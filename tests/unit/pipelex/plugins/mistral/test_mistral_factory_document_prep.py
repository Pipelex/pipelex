"""Tests for MistralFactory OCR document preparation: URI-to-chunk conversion and file upload to Mistral."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest

from pipelex.plugins.mistral.mistral_factory import MistralFactory
from pipelex.tools.misc.filetype_utils import FileType
from pipelex.tools.uri.prepared_file import PreparedFileBase64, PreparedFileHttpUrl, PreparedFileLocalPath

if TYPE_CHECKING:
    from pathlib import Path

    from mistralai.client import Mistral
    from pytest_mock import MockerFixture

PNG_FILE_TYPE = FileType(extension="png", mime="image/png")
PDF_FILE_TYPE = FileType(extension="pdf", mime="application/pdf")


def _make_mistral_client(mocker: MockerFixture, *, uploaded_file_id: str = "file-abc", signed_url: str = "https://signed.example.com/doc") -> Any:
    """Create a mock Mistral client with async files endpoints."""
    mock_client = mocker.MagicMock(name="mistral_client")
    uploaded_file = mocker.MagicMock(name="uploaded_file")
    uploaded_file.id = uploaded_file_id
    mock_client.files.upload_async = mocker.AsyncMock(return_value=uploaded_file)
    signed_url_response = mocker.MagicMock(name="signed_url_response")
    signed_url_response.url = signed_url
    mock_client.files.get_signed_url_async = mocker.AsyncMock(return_value=signed_url_response)
    return mock_client


@pytest.mark.asyncio(loop_scope="class")
class TestMistralFactoryDocumentPrep:
    # ---- make_mistral_image_url_chunk_from_uri ----

    @pytest.mark.parametrize(
        ("_topic", "prepared", "expected_url"),
        [
            (
                "http_url_kept_as_is",
                PreparedFileHttpUrl(url="https://example.com/pic.png"),
                "https://example.com/pic.png",
            ),
            (
                "base64_becomes_data_url",
                PreparedFileBase64(base64_data="QUJD", file_type=PNG_FILE_TYPE),
                "data:image/png;base64,QUJD",
            ),
        ],
    )
    async def test_make_mistral_image_url_chunk_from_uri(
        self,
        mocker: MockerFixture,
        _topic: str,
        prepared: Any,
        expected_url: str,
    ) -> None:
        """HTTP URLs are kept as-is and base64 files become data URLs; local paths are not requested from preparation."""
        prepare_mock = mocker.patch(
            "pipelex.plugins.mistral.mistral_factory.prepare_file_from_uri",
            return_value=prepared,
        )

        chunk = await MistralFactory.make_mistral_image_url_chunk_from_uri(uri="some://uri")

        assert chunk == {"type": "image_url", "image_url": expected_url}
        prepare_mock.assert_awaited_once_with(uri="some://uri", keep_http_url=True, keep_local_path=False)

    async def test_make_mistral_image_url_chunk_local_path_raises(self, mocker: MockerFixture) -> None:
        """An unexpected PreparedFileLocalPath (despite keep_local_path=False) raises a TypeError."""
        mocker.patch(
            "pipelex.plugins.mistral.mistral_factory.prepare_file_from_uri",
            return_value=PreparedFileLocalPath(path="/fake/dir/pic.png"),
        )

        with pytest.raises(TypeError, match="Unexpected PreparedFileLocalPath"):
            await MistralFactory.make_mistral_image_url_chunk_from_uri(uri="/fake/dir/pic.png")

    # ---- make_mistral_document_url_chunk_from_uri ----

    async def test_make_mistral_document_url_chunk_http_kept(self, mocker: MockerFixture) -> None:
        """An HTTP document URL is kept as-is and the client is never used."""
        prepare_mock = mocker.patch(
            "pipelex.plugins.mistral.mistral_factory.prepare_file_from_uri",
            return_value=PreparedFileHttpUrl(url="https://example.com/file.pdf"),
        )
        mock_client = _make_mistral_client(mocker)

        chunk = await MistralFactory.make_mistral_document_url_chunk_from_uri(
            mistral_client=cast("Mistral", mock_client),
            uri="https://example.com/file.pdf",
        )

        assert chunk == {"type": "document_url", "document_url": "https://example.com/file.pdf"}
        prepare_mock.assert_awaited_once_with(uri="https://example.com/file.pdf", keep_http_url=True, keep_local_path=True)
        mock_client.files.upload_async.assert_not_awaited()
        mock_client.files.get_signed_url_async.assert_not_awaited()

    async def test_make_mistral_document_url_chunk_local_path_uploads(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A local document is uploaded to Mistral for OCR and the chunk carries the signed URL of the uploaded file."""
        local_file = tmp_path / "scan.pdf"
        file_content = b"%PDF-1.7 fake pdf bytes"
        local_file.write_bytes(file_content)
        mocker.patch(
            "pipelex.plugins.mistral.mistral_factory.prepare_file_from_uri",
            return_value=PreparedFileLocalPath(path=str(local_file)),
        )
        mock_client = _make_mistral_client(mocker, uploaded_file_id="file-xyz", signed_url="https://signed.example.com/scan.pdf")

        chunk = await MistralFactory.make_mistral_document_url_chunk_from_uri(
            mistral_client=cast("Mistral", mock_client),
            uri=str(local_file),
        )

        assert chunk == {"type": "document_url", "document_url": "https://signed.example.com/scan.pdf"}
        mock_client.files.upload_async.assert_awaited_once_with(
            file={"file_name": "scan.pdf", "content": file_content},
            purpose="ocr",
        )
        mock_client.files.get_signed_url_async.assert_awaited_once_with(file_id="file-xyz")

    async def test_make_mistral_document_url_chunk_base64_two_pass(self, mocker: MockerFixture) -> None:
        """A base64 first-pass result triggers a second preparation pass with both keep flags False, yielding a data URL."""
        first_pass = PreparedFileBase64(base64_data="Rmly", file_type=PDF_FILE_TYPE)
        second_pass = PreparedFileBase64(base64_data="U2Vj", file_type=PDF_FILE_TYPE)
        prepare_mock = mocker.patch(
            "pipelex.plugins.mistral.mistral_factory.prepare_file_from_uri",
            side_effect=[first_pass, second_pass],
        )
        mock_client = _make_mistral_client(mocker)

        chunk = await MistralFactory.make_mistral_document_url_chunk_from_uri(
            mistral_client=cast("Mistral", mock_client),
            uri="data:application/pdf;base64,Rmly",
        )

        assert chunk == {"type": "document_url", "document_url": "data:application/pdf;base64,U2Vj"}
        assert prepare_mock.await_count == 2
        prepare_mock.assert_awaited_with(uri="data:application/pdf;base64,Rmly", keep_http_url=False, keep_local_path=False)
        mock_client.files.upload_async.assert_not_awaited()

    async def test_make_mistral_document_url_chunk_base64_second_pass_failure_raises(self, mocker: MockerFixture) -> None:
        """If the second preparation pass does not yield a base64 file, a TypeError is raised."""
        mocker.patch(
            "pipelex.plugins.mistral.mistral_factory.prepare_file_from_uri",
            side_effect=[
                PreparedFileBase64(base64_data="Rmly", file_type=PDF_FILE_TYPE),
                PreparedFileHttpUrl(url="https://example.com/file.pdf"),
            ],
        )
        mock_client = _make_mistral_client(mocker)

        with pytest.raises(TypeError, match="Failed to convert URI to base64"):
            await MistralFactory.make_mistral_document_url_chunk_from_uri(
                mistral_client=cast("Mistral", mock_client),
                uri="data:application/pdf;base64,Rmly",
            )

    # ---- upload_file_to_mistral_for_ocr ----

    async def test_upload_file_to_mistral_for_ocr(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """The file is read from disk and uploaded with its name, bytes content, and the ocr purpose; the uploaded id is returned."""
        local_file = tmp_path / "report.pdf"
        file_content = b"%PDF-1.7 report bytes"
        local_file.write_bytes(file_content)
        mock_client = _make_mistral_client(mocker, uploaded_file_id="file-123")

        uploaded_file_id = await MistralFactory.upload_file_to_mistral_for_ocr(
            mistral_client=cast("Mistral", mock_client),
            file_path=local_file,
        )

        assert uploaded_file_id == "file-123"
        mock_client.files.upload_async.assert_awaited_once_with(
            file={"file_name": "report.pdf", "content": file_content},
            purpose="ocr",
        )
