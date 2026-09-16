"""Unit tests for URL validation in DocumentContent."""

import pytest
from pytest_mock import MockerFixture

from pipelex.core.stuffs.document_content import DocumentContent


class TestDocumentContentUrlValidation:
    """Test that DocumentContent.validate_resources() validates URLs correctly."""

    def test_construction_does_not_validate_url(self) -> None:
        """Construction with any URL succeeds without validation."""
        doc = DocumentContent(url="https://this-domain-cannot-exist.invalid/file.pdf")
        assert doc.url == "https://this-domain-cannot-exist.invalid/file.pdf"

    def test_validate_resources_remote_url_is_not_probed(self, mocker: MockerFixture) -> None:
        """validate_resources() makes no HTTP request for a remote URL: the downstream extractor is the source of truth."""
        mock_head = mocker.patch("httpx.head")
        doc = DocumentContent(url="https://this-domain-cannot-exist.invalid/file.pdf")
        doc.validate_resources()
        mock_head.assert_not_called()

    def test_validate_resources_nonexistent_local_file(self) -> None:
        """validate_resources() raises ValueError for a non-existent local file."""
        doc = DocumentContent(url="/nonexistent/path/to/document.pdf")
        with pytest.raises(ValueError, match="does not exist"):
            doc.validate_resources()

    def test_validate_resources_existing_local_file(self) -> None:
        """validate_resources() passes for an existing local file."""
        doc = DocumentContent(url="pyproject.toml")
        doc.validate_resources()

    def test_validate_resources_base64_data_url_skips(self) -> None:
        """validate_resources() skips validation for base64 data URLs."""
        doc = DocumentContent(url="data:application/pdf;base64,abc123")
        doc.validate_resources()

    def test_validate_resources_pipelex_storage_url_skips(self) -> None:
        """validate_resources() skips validation for pipelex-storage URIs."""
        doc = DocumentContent(url="pipelex-storage://bucket/file.pdf")
        doc.validate_resources()
