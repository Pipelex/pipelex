"""Unit tests for URL validation in DocumentContent."""

import pytest
from pydantic import ValidationError

from pipelex.core.stuffs.document_content import DocumentContent


class TestDocumentContentUrlValidation:
    """Test that DocumentContent validates URLs on construction."""

    def test_valid_remote_url_passes(self) -> None:
        """A well-known reachable HTTP URL passes validation."""
        doc = DocumentContent(url="https://www.google.com/robots.txt")
        assert doc.url == "https://www.google.com/robots.txt"

    def test_unreachable_remote_url_raises_validation_error(self) -> None:
        """An HTTP URL on a non-existent domain raises a ValidationError."""
        with pytest.raises(ValidationError, match="could not be reached"):
            DocumentContent(url="https://this-domain-cannot-exist.invalid/file.pdf")

    def test_existing_local_file_passes(self) -> None:
        """A local file path that exists passes validation."""
        doc = DocumentContent(url="pyproject.toml")
        assert doc.url == "pyproject.toml"

    def test_nonexistent_local_file_raises_validation_error(self) -> None:
        """A local file path that does not exist raises a ValidationError."""
        with pytest.raises(ValidationError, match="does not exist"):
            DocumentContent(url="/nonexistent/path/to/document.pdf")

    def test_base64_data_url_skips_validation(self) -> None:
        """A base64 data URL is accepted without any check."""
        data_url = "data:application/pdf;base64,abc123"
        doc = DocumentContent(url=data_url)
        assert doc.url == data_url

    def test_pipelex_storage_url_skips_validation(self) -> None:
        """A pipelex-storage URI is accepted without any check."""
        storage_url = "pipelex-storage://bucket/file.pdf"
        doc = DocumentContent(url=storage_url)
        assert doc.url == storage_url
