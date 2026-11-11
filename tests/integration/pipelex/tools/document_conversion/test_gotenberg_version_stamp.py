import os
from http import HTTPStatus
from pathlib import Path

import httpx
import pytest
from typing_extensions import override

from pipelex.tools.document_conversion.gotenberg_converter import CONVERTER_VERSION_HEADER, GotenbergConverter
from tests.integration.pipelex.tools.document_conversion.test_data import DocumentConversionTestData


class _AnswerRecordingTransport(httpx.AsyncBaseTransport):
    """The network, keeping every answer the converter was sent, so a test reads the headers the PDF came with."""

    def __init__(self) -> None:
        self._transport = httpx.AsyncHTTPTransport()
        self.answers: list[httpx.Response] = []

    @override
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._transport.handle_async_request(request)
        self.answers.append(response)
        return response

    @override
    async def aclose(self) -> None:
        # The backend opens a client per attempt, which closes its transport on the way out: a retry gets a fresh pool.
        await self._transport.aclose()
        self._transport = httpx.AsyncHTTPTransport()


@pytest.mark.document_conversion
@pytest.mark.asyncio(loop_scope="class")
class TestGotenbergVersionStamp:
    async def test_a_pdf_is_stamped_with_the_version_on_the_answer_that_carried_it(self) -> None:
        """The stamp is the `Gotenberg-Version` header of the conversion's own `200`, the value `GET /version` answers too.

        `GET /version` is compared because it is the one oracle independent of the code under test, which never calls it.
        """
        gotenberg_url = os.environ.get(DocumentConversionTestData.GOTENBERG_URL_ENV_VAR)
        if not gotenberg_url:
            pytest.skip(f"no Gotenberg container: set {DocumentConversionTestData.GOTENBERG_URL_ENV_VAR}")
        transport = _AnswerRecordingTransport()
        converter = GotenbergConverter(
            base_url=gotenberg_url, timeout_seconds=360, budget_seconds=120, max_source_bytes=50_000_000, transport=transport
        )
        source_bytes = (Path(DocumentConversionTestData.DOCUMENTS_DIR) / "Office-Budget.xlsx").read_bytes()

        converted = await converter.convert_to_pdf(data=source_bytes, format_key="xlsx")

        pdf_answers = [answer for answer in transport.answers if answer.status_code == HTTPStatus.OK]
        assert len(pdf_answers) == 1
        assert converted.converter_version == pdf_answers[0].headers[CONVERTER_VERSION_HEADER]
        async with httpx.AsyncClient() as client:
            version_answer = await client.get(f"{gotenberg_url.rstrip('/')}/version")
        assert converted.converter_version == version_answer.text.strip()
