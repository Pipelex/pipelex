import base64
from pathlib import Path

import httpx
import pytest
from pytest_mock import MockerFixture

from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME
from pipelex.tools.uri.uri_resolver import make_base64_url_from_any_uri
from tests.cases import ImageTestCases


@pytest.mark.asyncio(loop_scope="class")
class TestMakeBase64UrlFromUriAsync:
    """Tests for make_base64_url_from_any_uri function."""

    async def test_local_path_returns_data_url(self) -> None:
        """Test that local file paths are converted to base64 data URLs."""
        file_path = ImageTestCases.IMAGE_FILE_PATH_PNG_1

        result = await make_base64_url_from_any_uri(file_path)

        # Should start with data URL prefix for PNG
        assert result.startswith("data:image/png;base64,")
        # Verify the base64 part is valid
        base64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(base64_part)
        # PNG magic bytes
        assert decoded[:8] == b"\x89PNG\r\n\x1a\n"

    async def test_local_path_jpeg_returns_data_url(self) -> None:
        """Test that JPEG files are converted correctly."""
        file_path = ImageTestCases.IMAGE_FILE_PATH_JPG_1

        result = await make_base64_url_from_any_uri(file_path)

        # Should start with data URL prefix for JPEG
        assert result.startswith("data:image/jpeg;base64,")
        # Verify the base64 part is valid
        base64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(base64_part)
        # JPEG magic bytes
        assert decoded[:2] == b"\xff\xd8"

    async def test_data_url_passthrough(self) -> None:
        """Test that existing data URLs are returned as-is."""
        original_data_url = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="

        result = await make_base64_url_from_any_uri(original_data_url)

        assert result == original_data_url

    async def test_data_url_passthrough_with_complex_content(self) -> None:
        """Test passthrough with a more complex data URL."""
        # A realistic base64 content string
        base64_content = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        original_data_url = f"data:image/png;base64,{base64_content}"

        result = await make_base64_url_from_any_uri(original_data_url)

        assert result == original_data_url

    async def test_pipelex_storage_converts_to_base64_data_url(self, mocker: MockerFixture) -> None:
        """Test that pipelex-storage:// URIs are loaded from storage and converted to base64 data URLs."""
        # Load real PNG bytes from test file
        with open(ImageTestCases.IMAGE_FILE_PATH_PNG_1, "rb") as file_handle:
            png_bytes = file_handle.read()

        # Mock the storage provider
        mock_storage = mocker.AsyncMock()
        mock_storage.load = mocker.AsyncMock(return_value=png_bytes)

        storage_uri = f"{PIPELEX_STORAGE_SCHEME}images/photo.png"
        result = await make_base64_url_from_any_uri(storage_uri, storage_provider=mock_storage)

        assert result.startswith("data:image/png;base64,")
        base64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(base64_part)
        assert decoded == png_bytes
        mock_storage.load.assert_called_once_with(uri=storage_uri)

    async def test_pipelex_storage_raises_value_error_without_storage(self) -> None:
        """Test that pipelex-storage:// URIs raise ValueError when no storage provider is given."""
        storage_uri = f"{PIPELEX_STORAGE_SCHEME}images/photo.png"

        with pytest.raises(ValueError, match="Cannot convert pipelex-storage"):
            await make_base64_url_from_any_uri(storage_uri)

    async def test_http_url_converts_to_base64_data_url(self, mocker: MockerFixture) -> None:
        """Test that HTTP URLs are fetched and converted to base64 data URLs."""
        # Load real PNG bytes from test file
        with open(ImageTestCases.IMAGE_FILE_PATH_PNG_1, "rb") as file_handle:
            png_bytes = file_handle.read()

        # Mock the HTTP fetch to return PNG bytes
        mocker.patch(
            "pipelex.tools.misc.base64_utils.fetch_file_from_url_httpx",
            return_value=png_bytes,
        )

        result = await make_base64_url_from_any_uri("https://example.com/image.png")

        assert result.startswith("data:image/png;base64,")
        base64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(base64_part)
        assert decoded == png_bytes

    async def test_https_url_converts_to_base64_data_url(self, mocker: MockerFixture) -> None:
        """Test that HTTPS URLs are fetched and converted to base64 data URLs."""
        # Load real JPEG bytes from test file
        with open(ImageTestCases.IMAGE_FILE_PATH_JPG_1, "rb") as file_handle:
            jpeg_bytes = file_handle.read()

        # Mock the HTTP fetch to return JPEG bytes
        mocker.patch(
            "pipelex.tools.misc.base64_utils.fetch_file_from_url_httpx",
            return_value=jpeg_bytes,
        )

        result = await make_base64_url_from_any_uri("https://secure.example.com/photo.jpg")

        assert result.startswith("data:image/jpeg;base64,")
        base64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(base64_part)
        assert decoded == jpeg_bytes

    async def test_http_url_propagates_network_errors(self, mocker: MockerFixture) -> None:
        """Test that HTTP network errors are propagated."""
        mocker.patch(
            "pipelex.tools.misc.base64_utils.fetch_file_from_url_httpx",
            side_effect=httpx.HTTPStatusError(
                message="404 Not Found",
                request=httpx.Request("GET", "https://example.com/not-found.png"),
                response=httpx.Response(404),
            ),
        )

        with pytest.raises(httpx.HTTPStatusError):
            await make_base64_url_from_any_uri("https://example.com/not-found.png")

    async def test_file_uri_converts_to_base64_data_url(self) -> None:
        """Test that file:// URIs are converted to base64 data URLs."""
        # file:// URIs need absolute paths
        absolute_path = Path(ImageTestCases.IMAGE_FILE_PATH_PNG_1).resolve()
        file_uri = f"file://{absolute_path}"

        result = await make_base64_url_from_any_uri(file_uri)

        assert result.startswith("data:image/png;base64,")
        base64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(base64_part)
        assert decoded[:8] == b"\x89PNG\r\n\x1a\n"
