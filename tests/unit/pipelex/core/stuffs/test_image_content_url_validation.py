"""Unit tests for URL validation in ImageContent."""

import pytest

from pipelex.core.stuffs.image_content import ImageContent


class TestImageContentUrlValidation:
    """Test that ImageContent.validate_resources() validates URLs correctly."""

    def test_construction_does_not_validate_url(self) -> None:
        """Construction with any URL succeeds without validation."""
        img = ImageContent(url="https://this-domain-cannot-exist.invalid/image.png")
        assert img.url == "https://this-domain-cannot-exist.invalid/image.png"

    def test_validate_resources_unreachable_remote_url(self) -> None:
        """validate_resources() raises ValueError for an unreachable HTTP URL."""
        img = ImageContent(url="https://this-domain-cannot-exist.invalid/image.png")
        with pytest.raises(ValueError, match="could not be reached"):
            img.validate_resources()

    def test_validate_resources_nonexistent_local_file(self) -> None:
        """validate_resources() raises ValueError for a non-existent local file."""
        img = ImageContent(url="/nonexistent/path/to/image.png")
        with pytest.raises(ValueError, match="does not exist"):
            img.validate_resources()

    def test_validate_resources_existing_local_file(self) -> None:
        """validate_resources() passes for an existing local file."""
        img = ImageContent(url="pyproject.toml")
        img.validate_resources()

    def test_validate_resources_base64_data_url_skips(self) -> None:
        """validate_resources() skips validation for base64 data URLs."""
        img = ImageContent(url="data:image/png;base64,abc123")
        img.validate_resources()

    def test_validate_resources_pipelex_storage_url_skips(self) -> None:
        """validate_resources() skips validation for pipelex-storage URIs."""
        img = ImageContent(url="pipelex-storage://bucket/image.png")
        img.validate_resources()
