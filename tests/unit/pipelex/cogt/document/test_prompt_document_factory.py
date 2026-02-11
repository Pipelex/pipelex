import pytest

from pipelex.cogt.document.prompt_document import (
    PromptDocumentBase64,
    PromptDocumentBinary,
    PromptDocumentUri,
)
from pipelex.cogt.document.prompt_document_factory import PromptDocumentFactory
from pipelex.cogt.exceptions import PromptDocumentFactoryError
from pipelex.urls import URLs


class TestPromptDocumentFactory:
    """Tests for PromptDocumentFactory."""

    def test_make_from_uri(self) -> None:
        """Test creating PromptDocumentUri from a URI string."""
        result = PromptDocumentFactory.make_prompt_document(uri=URLs.pdf_example_1)

        assert isinstance(result, PromptDocumentUri)
        assert result.uri == URLs.pdf_example_1

    def test_make_from_file_path(self) -> None:
        """Test creating PromptDocumentUri from a local file path."""
        result = PromptDocumentFactory.make_prompt_document(uri="/path/to/document.pdf")

        assert isinstance(result, PromptDocumentUri)
        assert result.uri == "/path/to/document.pdf"

    def test_make_from_base64_data(self) -> None:
        """Test creating PromptDocumentBase64 from base64 string."""
        base64_data = "JVBERi0xLjQK"  # PDF magic bytes in base64

        result = PromptDocumentFactory.make_prompt_document(base64_data=base64_data)

        assert isinstance(result, PromptDocumentBase64)
        assert result.base64_data == base64_data

    def test_make_from_raw_bytes(self) -> None:
        """Test creating PromptDocumentBinary from raw bytes."""
        raw_bytes = b"%PDF-1.4\n"  # PDF magic bytes

        result = PromptDocumentFactory.make_prompt_document(raw_bytes=raw_bytes)

        assert isinstance(result, PromptDocumentBinary)
        assert result.raw_bytes == raw_bytes

    def test_make_from_data_url_extracts_base64(self) -> None:
        """Test that data URLs are converted to PromptDocumentBase64."""
        # A data URL containing PDF-like content
        data_url = "data:application/pdf;base64,JVBERi0xLjQK"

        result = PromptDocumentFactory.make_prompt_document(uri=data_url)

        # Should extract the base64 portion and return PromptDocumentBase64
        assert isinstance(result, PromptDocumentBase64)
        assert result.base64_data == "JVBERi0xLjQK"

    def test_make_with_mime_type(self) -> None:
        """Test creating PromptDocumentUri with explicit mime_type."""
        result = PromptDocumentFactory.make_prompt_document(
            uri=URLs.pdf_example_1,
            mime_type="application/pdf",
        )

        assert isinstance(result, PromptDocumentUri)
        assert result.mime_type == "application/pdf"

    def test_raises_without_input(self) -> None:
        """Test error when no valid input provided."""
        with pytest.raises(PromptDocumentFactoryError):
            PromptDocumentFactory.make_prompt_document()

    def test_priority_raw_bytes_over_base64(self) -> None:
        """Test that raw_bytes takes priority over base64_data."""
        raw_bytes = b"%PDF-1.4\n"
        base64_data = "JVBERi0xLjQK"

        result = PromptDocumentFactory.make_prompt_document(
            raw_bytes=raw_bytes,
            base64_data=base64_data,
        )

        assert isinstance(result, PromptDocumentBinary)

    def test_priority_base64_over_uri(self) -> None:
        """Test that base64_data takes priority over uri."""
        base64_data = "JVBERi0xLjQK"
        uri = URLs.pdf_example_1

        result = PromptDocumentFactory.make_prompt_document(
            base64_data=base64_data,
            uri=uri,
        )

        assert isinstance(result, PromptDocumentBase64)
