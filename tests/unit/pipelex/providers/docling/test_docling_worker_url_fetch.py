"""Docling reads every source that is not a local file from a temp file the runtime wrote.

An http(s) URL is downloaded by the runtime's guarded fetch helper, never by Docling, and the
temp file is named with an extension Docling can read the format from.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.cogt.exceptions import ExtractJobFailureError
from pipelex.providers.docling.docling_extract_worker import DoclingExtractWorker
from pipelex.providers.docling.docling_sdk import DoclingSdk
from pipelex.tools.network.exceptions import SsrfBlockedError
from pipelex.tools.storage.storage_provider_abstract import StoredData

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

WORKER_MODULE = "pipelex.providers.docling.docling_extract_worker"
FETCH_TARGET = f"{WORKER_MODULE}.fetch_file_and_content_type_from_url_httpx"
PDF_BYTES = b"%PDF-1.4\n%fake\n"
HTML_BYTES = b"<html><body><h1>Quarterly report</h1><p>Revenue grew.</p></body></html>"
CSV_BYTES = b"name,qty\nbolt,3\n"
MARKDOWN_BYTES = b"# Title\n\nSome *markdown* text.\n"


def _make_worker(mocker: MockerFixture, *, docling_sdk: DoclingSdk | None = None) -> DoclingExtractWorker:
    worker = object.__new__(DoclingExtractWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-docling"
    mock_model.name = "docling"
    worker.inference_model = mock_model
    worker.docling_sdk = docling_sdk or mocker.MagicMock()
    return worker


def _data_url(*, mime_type: str, body: bytes) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(body).decode('ascii')}"


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

        mocker.patch(f"{WORKER_MODULE}.asyncio.to_thread", new_callable=mocker.AsyncMock, side_effect=record_source)

        with pytest.raises(ExtractJobFailureError, match="stop after recording the source"):
            await worker._extract_from_source(source_uri="https://example.com/doc.pdf")  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        fetch_mock.assert_awaited_once_with("https://example.com/doc.pdf")
        assert len(docling_sources) == 1
        assert docling_sources[0] != "https://example.com/doc.pdf"
        assert docling_sources[0].endswith(".pdf")
        assert not Path(docling_sources[0]).exists()

    @pytest.mark.parametrize(
        ("url", "expected_download_url"),
        [
            ("https://docs.google.com/document/d/abc_-1/edit", "https://docs.google.com/document/d/abc_-1/export?format=docx"),
            ("https://docs.google.com/spreadsheets/d/abc/edit#gid=0", "https://docs.google.com/spreadsheets/d/abc/export?format=xlsx"),
            ("https://docs.google.com/presentation/d/abc/edit", "https://docs.google.com/presentation/d/abc/export?format=pptx"),
            ("https://drive.google.com/file/d/abc/view?usp=sharing", "https://drive.google.com/uc?export=download&id=abc"),
            ("https://example.com/doc.pdf", "https://example.com/doc.pdf"),
        ],
    )
    async def test_a_google_link_is_downloaded_from_its_export_url(self, mocker: MockerFixture, url: str, expected_download_url: str) -> None:
        worker = _make_worker(mocker)
        fetch_mock = mocker.patch(FETCH_TARGET, new_callable=mocker.AsyncMock, return_value=(PDF_BYTES, "application/pdf"))
        mocker.patch(f"{WORKER_MODULE}.asyncio.to_thread", new_callable=mocker.AsyncMock, side_effect=ValueError("stop"))

        with pytest.raises(ExtractJobFailureError):
            await worker._extract_from_source(source_uri=url)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        fetch_mock.assert_awaited_once_with(expected_download_url)

    @pytest.mark.parametrize(
        ("named_after", "media_type", "expected_suffix"),
        [
            # The URL's or storage key's own extension wins when Docling knows it
            ("https://example.com/data.csv", "text/plain", ".csv"),
            ("https://example.com/notes/readme.md?raw=1", "text/plain; charset=utf-8", ".md"),
            ("pipelex-storage://scope/assets/abc123.html", None, ".html"),
            # Otherwise the declared media type names the format
            ("https://example.com/page", "text/html", ".html"),
            ("https://example.com/docs/v1.2", "text/markdown", ".md"),
            ("https://example.com/report?format=x.pdf", "text/csv", ".csv"),
            (None, "text/markdown", ".md"),
            # With neither, the file gets no extension and Docling sniffs the content
            ("https://example.com/download", "application/octet-stream", ""),
            ("https://example.com/download", None, ""),
            (None, None, ""),
        ],
    )
    async def test_the_temp_file_is_named_so_docling_can_tell_its_format(
        self,
        named_after: str | None,
        media_type: str | None,
        expected_suffix: str,
    ) -> None:
        suffix = DoclingExtractWorker._suffix_for_docling(named_after=named_after, media_type=media_type)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert suffix == expected_suffix

    @pytest.mark.parametrize(
        ("source_uri", "media_type", "body", "expected_text"),
        [
            ("https://example.com/page", "text/html", HTML_BYTES, "Revenue grew."),
            ("https://example.com/stock.csv", "text/plain", CSV_BYTES, "bolt"),
            ("https://example.com/readme.md", "text/plain", MARKDOWN_BYTES, "markdown"),
            ("pipelex-storage://scope/assets/abc123.md", None, MARKDOWN_BYTES, "markdown"),
            ("pipelex-storage://scope/assets/abc123", "text/markdown", MARKDOWN_BYTES, "markdown"),
            (_data_url(mime_type="text/csv", body=CSV_BYTES), None, CSV_BYTES, "bolt"),
            (_data_url(mime_type="text/markdown", body=MARKDOWN_BYTES), None, MARKDOWN_BYTES, "markdown"),
        ],
    )
    async def test_a_text_format_source_is_extracted_by_docling(
        self,
        mocker: MockerFixture,
        real_docling_sdk: DoclingSdk,
        source_uri: str,
        media_type: str | None,
        body: bytes,
        expected_text: str,
    ) -> None:
        worker = _make_worker(mocker, docling_sdk=real_docling_sdk)
        mocker.patch(FETCH_TARGET, new_callable=mocker.AsyncMock, return_value=(body, media_type))
        storage_provider = mocker.MagicMock()
        storage_provider.load_with_metadata = mocker.AsyncMock(return_value=StoredData(data=body, mime_type=media_type))
        mocker.patch(f"{WORKER_MODULE}.get_storage_provider", return_value=storage_provider)

        extract_output = await worker._extract_from_source(source_uri=source_uri)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert list(extract_output.pages) == [0]
        assert expected_text in (extract_output.pages[0].text or "")

    async def test_a_private_url_is_refused_before_docling_runs(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        to_thread_mock = mocker.patch(f"{WORKER_MODULE}.asyncio.to_thread", new_callable=mocker.AsyncMock)

        with pytest.raises(SsrfBlockedError):
            await worker._extract_from_source(source_uri="http://127.0.0.1:9/doc.pdf")  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        to_thread_mock.assert_not_awaited()
