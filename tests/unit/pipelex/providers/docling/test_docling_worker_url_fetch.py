"""Docling never fetches a URL itself: the runtime's guarded fetch helper downloads it first."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.cogt.exceptions import ExtractJobFailureError
from pipelex.providers.docling.docling_extract_worker import DoclingExtractWorker
from pipelex.providers.docling.docling_sdk import DoclingSdk
from pipelex.tools.network.exceptions import SsrfBlockedError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

FETCH_TARGET = "pipelex.providers.docling.docling_extract_worker.fetch_file_and_content_type_from_url_httpx"
PDF_BYTES = b"%PDF-1.4\n%fake\n"


def _make_worker(mocker: MockerFixture, *, docling_sdk: DoclingSdk | None = None) -> DoclingExtractWorker:
    worker = object.__new__(DoclingExtractWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-docling"
    mock_model.name = "docling"
    worker.inference_model = mock_model
    worker.docling_sdk = docling_sdk or mocker.MagicMock()
    return worker


@pytest.fixture(scope="module")
def real_docling_sdk() -> DoclingSdk:
    return DoclingSdk()


@pytest.mark.asyncio(loop_scope="class")
class TestDoclingWorkerUrlFetch:
    async def test_an_http_url_reaches_docling_as_a_downloaded_file(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        fetch_mock = mocker.patch(FETCH_TARGET, new_callable=mocker.AsyncMock, return_value=(PDF_BYTES, "application/pdf"))
        docling_sources: list[str] = []

        def record_source(_convert: object, docling_source: str) -> object:
            docling_sources.append(docling_source)
            assert Path(docling_source).read_bytes() == PDF_BYTES
            stop_msg = "stop after recording the source"
            raise ValueError(stop_msg)

        mocker.patch("pipelex.providers.docling.docling_extract_worker.asyncio.to_thread", new_callable=mocker.AsyncMock, side_effect=record_source)

        with pytest.raises(ExtractJobFailureError, match="stop after recording the source"):
            await worker._extract_from_source(source_uri="https://example.com/doc.pdf")  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        fetch_mock.assert_awaited_once_with("https://example.com/doc.pdf")
        assert len(docling_sources) == 1
        assert docling_sources[0] != "https://example.com/doc.pdf"
        assert docling_sources[0].endswith(".pdf")
        assert not Path(docling_sources[0]).exists()

    @pytest.mark.parametrize(
        ("url", "media_type", "expected_suffix"),
        [
            # The URL path's own extension wins, as it did when Docling fetched URLs itself
            ("https://example.com/data.csv", "text/plain", ".csv"),
            ("https://example.com/notes/readme.md?raw=1", "text/plain; charset=utf-8", ".md"),
            # Without one, the declared content type names the format
            ("https://example.com/page", "text/html", ".html"),
            ("https://example.com/report?format=x.pdf", "text/markdown", ".md"),
            # A suffix that is not a plain extension never names a temp file
            ("https://example.com/odd.p%20df", "text/csv", ".csv"),
            # With neither, the file gets no extension and Docling sniffs the content
            ("https://example.com/download", None, ""),
            ("https://example.com/download", "text/x-unheard-of", ""),
        ],
    )
    async def test_the_download_is_named_so_docling_can_tell_its_format(self, url: str, media_type: str | None, expected_suffix: str) -> None:
        suffix = DoclingExtractWorker._suffix_for_downloaded_url(url=url, media_type=media_type)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert suffix == expected_suffix

    @pytest.mark.parametrize(
        ("url", "media_type", "body", "expected_text"),
        [
            ("https://example.com/page", "text/html", b"<html><body><h1>Quarterly report</h1><p>Revenue grew.</p></body></html>", "Revenue grew."),
            ("https://example.com/stock.csv", "text/plain", b"name,qty\nbolt,3\n", "bolt"),
            ("https://example.com/readme.md", "text/plain", b"# Title\n\nSome *markdown* text.\n", "markdown"),
        ],
    )
    async def test_a_text_format_url_is_extracted_by_docling(
        self,
        mocker: MockerFixture,
        real_docling_sdk: DoclingSdk,
        url: str,
        media_type: str,
        body: bytes,
        expected_text: str,
    ) -> None:
        worker = _make_worker(mocker, docling_sdk=real_docling_sdk)
        mocker.patch(FETCH_TARGET, new_callable=mocker.AsyncMock, return_value=(body, media_type))

        extract_output = await worker._extract_from_source(source_uri=url)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert list(extract_output.pages) == [0]
        assert expected_text in (extract_output.pages[0].text or "")

    async def test_a_private_url_is_refused_before_docling_runs(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        to_thread_mock = mocker.patch("pipelex.providers.docling.docling_extract_worker.asyncio.to_thread", new_callable=mocker.AsyncMock)

        with pytest.raises(SsrfBlockedError):
            await worker._extract_from_source(source_uri="http://127.0.0.1:9/doc.pdf")  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        to_thread_mock.assert_not_awaited()
