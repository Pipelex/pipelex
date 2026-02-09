import base64

import pytest

from pipelex.tools.misc.base64_utils import (
    extract_base64_str_from_base64_url_if_possible,
    is_prefixed_base64_url,
    load_binary_as_base64,
    make_base64_url,
    make_base64_url_from_path,
    strip_base64_str_if_needed,
)
from pipelex.tools.misc.filetype_utils import FileType
from pipelex.urls import URLs
from tests.cases import FileHelperTestCases, ImageTestCases


class TestBase64Utils:
    """Tests for base64 utils."""

    @pytest.mark.asyncio
    async def test_load_binary_as_base64_async(self) -> None:
        """Test asynchronous loading of binary file as base64 string."""
        file_path = FileHelperTestCases.TEST_IMAGE
        with open(file_path, "rb") as file_handle:
            expected = base64.b64encode(file_handle.read()).decode("ascii")

        result = await load_binary_as_base64(path=file_path)

        assert result == expected
        assert isinstance(result, str)

    def test_make_base64_url_png(self) -> None:
        """Test creating a base64 data URL for PNG."""
        base64_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
        file_type = FileType(extension="png", mime="image/png")

        result = make_base64_url(base64_data=base64_data, file_type=file_type)

        assert result == "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"

    def test_make_base64_url_jpeg(self) -> None:
        """Test creating a base64 data URL for JPEG."""
        base64_data = "/9j/4AAQSkZJRgABAQAAAQABAAD"
        file_type = FileType(extension="jpg", mime="image/jpeg")

        result = make_base64_url(base64_data=base64_data, file_type=file_type)

        assert result == "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD"

    def test_make_base64_url_pdf(self) -> None:
        """Test creating a base64 data URL for PDF."""
        base64_data = "JVBERi0xLjQK"
        file_type = FileType(extension="pdf", mime="application/pdf")

        result = make_base64_url(base64_data=base64_data, file_type=file_type)

        assert result == "data:application/pdf;base64,JVBERi0xLjQK"

    def test_make_base64_url_webp(self) -> None:
        """Test creating a base64 data URL for WebP."""
        base64_data = "UklGRhYAAABXRUJQ"
        file_type = FileType(extension="webp", mime="image/webp")

        result = make_base64_url(base64_data=base64_data, file_type=file_type)

        assert result == "data:image/webp;base64,UklGRhYAAABXRUJQ"

    @pytest.mark.asyncio
    async def test_make_base64_url_from_path_async_png(self) -> None:
        """Test async creating base64 URL from PNG file path."""
        file_path = ImageTestCases.IMAGE_FILE_PATH_PNG_1

        result = await make_base64_url_from_path(path=file_path)

        assert result.startswith("data:image/png;base64,")
        base64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(base64_part)
        assert decoded[:8] == b"\x89PNG\r\n\x1a\n"

    @pytest.mark.asyncio
    async def test_make_base64_url_from_path_async_jpeg(self) -> None:
        """Test async creating base64 URL from JPEG file path."""
        file_path = ImageTestCases.IMAGE_FILE_PATH_JPG_1

        result = await make_base64_url_from_path(path=file_path)

        assert result.startswith("data:image/jpeg;base64,")
        base64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(base64_part)
        assert decoded[:2] == b"\xff\xd8"

    @pytest.mark.parametrize(
        "url",
        [
            "data:image/png;base64,iVBORw0KGgo=",
            "data:image/jpeg;base64,/9j/4AAQ",
            "data:application/pdf;base64,JVBERi0=",
            "data:image/webp;base64,UklGRhYA",
            "data:text/plain;base64,SGVsbG8=",
        ],
    )
    def test_is_prefixed_base64_url_returns_true(self, url: str) -> None:
        """Test that valid base64 data URLs return True."""
        assert is_prefixed_base64_url(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            URLs.png_example_1,
            URLs.jpg_example_1,
            "/path/to/file.png",
            "relative/path.jpg",
            "data:text/plain,Hello",  # No ;base64,
            "data:image/png,raw_data",  # No ;base64,
            "",
            "base64,something",  # Missing data: prefix
        ],
    )
    def test_is_prefixed_base64_url_returns_false(self, url: str) -> None:
        """Test that non-base64 URLs return False."""
        assert is_prefixed_base64_url(url) is False

    def test_strip_full_data_url(self) -> None:
        """Test stripping full data URL prefix."""
        base64_str = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="

        result = strip_base64_str_if_needed(base64_str)

        assert result == "iVBORw0KGgoAAAANSUhEUg=="

    def test_strip_simple_comma_prefix(self) -> None:
        """Test stripping when there's just a comma prefix."""
        base64_str = "image/png;base64,iVBORw0KGgoAAAANSUhEUg=="

        result = strip_base64_str_if_needed(base64_str)

        assert result == "iVBORw0KGgoAAAANSUhEUg=="

    def test_no_strip_needed(self) -> None:
        """Test that plain base64 strings are returned as-is."""
        base64_str = "iVBORw0KGgoAAAANSUhEUg=="

        result = strip_base64_str_if_needed(base64_str)

        assert result == "iVBORw0KGgoAAAANSUhEUg=="

    def test_strip_with_different_mime_types(self) -> None:
        """Test stripping with various MIME types."""
        base64_str = "data:application/pdf;base64,JVBERi0xLjQK"

        result = strip_base64_str_if_needed(base64_str)

        assert result == "JVBERi0xLjQK"

    def test_extract_png_base64_url(self) -> None:
        """Test extracting from PNG data URL."""
        url = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="

        result = extract_base64_str_from_base64_url_if_possible(url)

        assert result is not None
        base64_str, mime_type = result
        assert base64_str == "iVBORw0KGgoAAAANSUhEUg=="
        assert mime_type == "image/png"

    def test_extract_jpeg_base64_url(self) -> None:
        """Test extracting from JPEG data URL."""
        url = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD"

        result = extract_base64_str_from_base64_url_if_possible(url)

        assert result is not None
        base64_str, mime_type = result
        assert base64_str == "/9j/4AAQSkZJRgABAQAAAQABAAD"
        assert mime_type == "image/jpeg"

    def test_extract_pdf_base64_url(self) -> None:
        """Test extracting from PDF data URL."""
        url = "data:application/pdf;base64,JVBERi0xLjQK"

        result = extract_base64_str_from_base64_url_if_possible(url)

        assert result is not None
        base64_str, mime_type = result
        assert base64_str == "JVBERi0xLjQK"
        assert mime_type == "application/pdf"

    def test_returns_none_for_non_data_url(self) -> None:
        """Test that non-data URLs return None."""
        url = URLs.png_example_1

        result = extract_base64_str_from_base64_url_if_possible(url)

        assert result is None

    def test_returns_none_for_non_base64_data_url(self) -> None:
        """Test that data URLs without ;base64, return None."""
        url = "data:text/plain,Hello%20World"

        result = extract_base64_str_from_base64_url_if_possible(url)

        assert result is None

    def test_returns_none_for_empty_string(self) -> None:
        """Test that empty string returns None."""
        result = extract_base64_str_from_base64_url_if_possible("")

        assert result is None

    def test_returns_none_for_local_path(self) -> None:
        """Test that local paths return None."""
        result = extract_base64_str_from_base64_url_if_possible("/path/to/file.png")

        assert result is None
