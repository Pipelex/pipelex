"""Unit tests for URL validation in ImageContent."""

import pytest
from pydantic import ValidationError

from pipelex.core.stuffs.image_content import ImageContent


class TestImageContentUrlValidation:
    """Test that ImageContent validates URLs on construction."""

    def test_valid_remote_url_passes(self) -> None:
        """A well-known reachable HTTP URL passes validation."""
        img = ImageContent(url="https://www.google.com/robots.txt")
        assert img.url == "https://www.google.com/robots.txt"

    def test_unreachable_remote_url_raises_validation_error(self) -> None:
        """An HTTP URL on a non-existent domain raises a ValidationError."""
        with pytest.raises(ValidationError, match="could not be reached"):
            ImageContent(url="https://this-domain-cannot-exist.invalid/image.png")

    def test_existing_local_file_passes(self) -> None:
        """A local file path that exists passes validation."""
        img = ImageContent(url="pyproject.toml")
        assert img.url == "pyproject.toml"

    def test_nonexistent_local_file_raises_validation_error(self) -> None:
        """A local file path that does not exist raises a ValidationError."""
        with pytest.raises(ValidationError, match="does not exist"):
            ImageContent(url="/nonexistent/path/to/image.png")

    def test_base64_data_url_skips_validation(self) -> None:
        """A base64 data URL is accepted without any check."""
        data_url = "data:image/png;base64,abc123"
        img = ImageContent(url=data_url)
        assert img.url == data_url

    def test_pipelex_storage_url_skips_validation(self) -> None:
        """A pipelex-storage URI is accepted without any check."""
        storage_url = "pipelex-storage://bucket/image.png"
        img = ImageContent(url=storage_url)
        assert img.url == storage_url
