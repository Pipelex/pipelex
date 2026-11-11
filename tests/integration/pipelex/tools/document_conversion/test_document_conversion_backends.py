import os
from http import HTTPStatus
from pathlib import Path

import httpx
import pypdfium2 as pdfium
import pytest
from typing_extensions import override

from pipelex.tools.document_conversion.document_converter_protocol import PDF_MAGIC, DocumentConverterProtocol
from pipelex.tools.document_conversion.exceptions import DocumentUnreadableByConverterError
from pipelex.tools.document_conversion.gotenberg_converter import CONVERTER_VERSION_HEADER, GotenbergConverter
from tests.integration.pipelex.tools.document_conversion.test_data import DocumentConversionTestData, OfficeFileCase


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


def _read_pdf(*, pdf_bytes: bytes) -> tuple[int, str]:
    """The PDF's page count and the text of its first page."""
    document = pdfium.PdfDocument(pdf_bytes)
    try:
        page_count = len(document)
        text_page = document[0].get_textpage()
        first_page_text: str = text_page.get_text_bounded()  # pyright: ignore[reportUnknownMemberType]
    finally:
        document.close()
    return page_count, first_page_text


@pytest.mark.document_conversion
@pytest.mark.asyncio(loop_scope="class")
class TestDocumentConversionBackends:
    @pytest.mark.parametrize("office_file", DocumentConversionTestData.OFFICE_FILES, ids=lambda case: case.file_name)
    async def test_an_office_file_converts_to_its_printed_pages(
        self, document_converter: DocumentConverterProtocol, office_file: OfficeFileCase
    ) -> None:
        source_bytes = (Path(DocumentConversionTestData.DOCUMENTS_DIR) / office_file.file_name).read_bytes()

        converted = await document_converter.convert_to_pdf(data=source_bytes, format_key=office_file.format_key)

        assert converted.pdf_bytes.startswith(PDF_MAGIC)
        assert converted.converter_name == document_converter.converter_name
        assert converted.converter_version
        page_count, first_page_text = _read_pdf(pdf_bytes=converted.pdf_bytes)
        assert page_count == office_file.page_count
        for word in office_file.first_page_words:
            assert word in first_page_text

    async def test_a_truncated_file_is_unreadable(self, document_converter: DocumentConverterProtocol) -> None:
        """Gotenberg answers a truncated Word file `500` (8.40) or `400` (9.2), and soffice writes no PDF of it."""
        source_bytes = (Path(DocumentConversionTestData.DOCUMENTS_DIR) / "CV-ELIAS-THORNE.docx").read_bytes()

        with pytest.raises(DocumentUnreadableByConverterError):
            await document_converter.convert_to_pdf(data=source_bytes[:3000], format_key="docx")


@pytest.mark.document_conversion
@pytest.mark.asyncio(loop_scope="class")
class TestGotenbergVersionStamp:
    async def test_a_pdf_is_stamped_with_the_version_on_the_answer_that_carried_it(self) -> None:
        """The stamp is the `Gotenberg-Version` header of the conversion's own `200`, the value `GET /version` answers too."""
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
