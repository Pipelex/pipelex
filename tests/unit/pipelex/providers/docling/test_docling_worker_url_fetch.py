"""Docling never fetches a URL itself: the runtime's guarded fetch helper downloads it first."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.cogt.exceptions import ExtractJobFailureError
from pipelex.providers.docling.docling_extract_worker import DoclingExtractWorker
from pipelex.tools.network.exceptions import SsrfBlockedError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

PDF_BYTES = b"%PDF-1.4\n%fake\n"


def _make_worker(mocker: MockerFixture) -> DoclingExtractWorker:
    worker = object.__new__(DoclingExtractWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-docling"
    mock_model.name = "docling"
    worker.inference_model = mock_model
    worker.docling_sdk = mocker.MagicMock()
    return worker


@pytest.mark.asyncio(loop_scope="class")
class TestDoclingWorkerUrlFetch:
    async def test_an_http_url_reaches_docling_as_a_downloaded_file(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        fetch_mock = mocker.patch(
            "pipelex.cogt.file.file_preparation_utils.fetch_file_from_url_httpx",
            new_callable=mocker.AsyncMock,
            return_value=PDF_BYTES,
        )
        docling_sources: list[str] = []

        def record_source(_convert: object, docling_source: str) -> object:
            docling_sources.append(docling_source)
            assert Path(docling_source).read_bytes() == PDF_BYTES
            stop_msg = "stop after recording the source"
            raise ValueError(stop_msg)

        mocker.patch("pipelex.providers.docling.docling_extract_worker.asyncio.to_thread", new_callable=mocker.AsyncMock, side_effect=record_source)

        with pytest.raises(ExtractJobFailureError, match="stop after recording the source"):
            await worker._extract_from_source(source_uri="https://example.com/doc.pdf")  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        fetch_mock.assert_awaited_once_with(url="https://example.com/doc.pdf")
        assert len(docling_sources) == 1
        assert docling_sources[0] != "https://example.com/doc.pdf"
        assert not Path(docling_sources[0]).exists()

    async def test_a_private_url_is_refused_before_docling_runs(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        to_thread_mock = mocker.patch("pipelex.providers.docling.docling_extract_worker.asyncio.to_thread", new_callable=mocker.AsyncMock)

        with pytest.raises(SsrfBlockedError):
            await worker._extract_from_source(source_uri="http://127.0.0.1:9/doc.pdf")  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        to_thread_mock.assert_not_awaited()
