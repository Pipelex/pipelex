import base64

import httpx
import pytest
from pytest_mock import MockerFixture

from pipelex.tools.misc.base64_utils import make_base64_url_from_http_url
from pipelex.urls import URLs
from tests.cases import ImageTestCases


@pytest.mark.asyncio(loop_scope="class")
class TestMakeBase64UrlFromHttpUrlAsync:
    """Tests for make_base64_url_from_http_url function with mocked HTTP calls."""

    async def test_converts_png_url_to_base64_data_url(self, mocker: MockerFixture) -> None:
        """Test that PNG HTTP URLs are converted to base64 data URLs."""
        # Load real PNG bytes from test file
        with open(ImageTestCases.IMAGE_FILE_PATH_PNG_1, "rb") as file_handle:
            png_bytes = file_handle.read()

        # Mock the HTTP fetch to return PNG bytes
        mocker.patch(
            "pipelex.tools.misc.base64_utils.fetch_file_from_url_httpx",
            return_value=png_bytes,
        )

        result = await make_base64_url_from_http_url(url=URLs.png_example_1)

        assert result.startswith("data:image/png;base64,")
        # Verify the base64 part decodes to original PNG bytes
        base64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(base64_part)
        assert decoded == png_bytes

    async def test_converts_jpeg_url_to_base64_data_url(self, mocker: MockerFixture) -> None:
        """Test that JPEG HTTP URLs are converted to base64 data URLs."""
        # Load real JPEG bytes from test file
        with open(ImageTestCases.IMAGE_FILE_PATH_JPG_1, "rb") as file_handle:
            jpeg_bytes = file_handle.read()

        # Mock the HTTP fetch to return JPEG bytes
        mocker.patch(
            "pipelex.tools.misc.base64_utils.fetch_file_from_url_httpx",
            return_value=jpeg_bytes,
        )

        result = await make_base64_url_from_http_url(url=URLs.jpg_example_1)

        assert result.startswith("data:image/jpeg;base64,")
        # Verify the base64 part decodes to original JPEG bytes
        base64_part = result.split(",", 1)[1]
        decoded = base64.b64decode(base64_part)
        assert decoded == jpeg_bytes

    async def test_propagates_http_error_on_404(self, mocker: MockerFixture) -> None:
        """Test that HTTP 404 errors are propagated."""
        mocker.patch(
            "pipelex.tools.misc.base64_utils.fetch_file_from_url_httpx",
            side_effect=httpx.HTTPStatusError(
                message="404 Not Found",
                request=httpx.Request("GET", URLs.png_example_1),
                response=httpx.Response(404),
            ),
        )

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await make_base64_url_from_http_url(url=URLs.png_example_1)

        assert exc_info.value.response.status_code == 404

    async def test_propagates_http_error_on_500(self, mocker: MockerFixture) -> None:
        """Test that HTTP 500 errors are propagated."""
        mocker.patch(
            "pipelex.tools.misc.base64_utils.fetch_file_from_url_httpx",
            side_effect=httpx.HTTPStatusError(
                message="500 Internal Server Error",
                request=httpx.Request("GET", URLs.png_example_1),
                response=httpx.Response(500),
            ),
        )

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await make_base64_url_from_http_url(url=URLs.png_example_1)

        assert exc_info.value.response.status_code == 500

    async def test_propagates_connection_error(self, mocker: MockerFixture) -> None:
        """Test that connection errors are propagated."""
        mocker.patch(
            "pipelex.tools.misc.base64_utils.fetch_file_from_url_httpx",
            side_effect=httpx.ConnectError("Connection refused"),
        )

        with pytest.raises(httpx.ConnectError):
            await make_base64_url_from_http_url(url="https://unreachable.example.com/image.png")

    async def test_propagates_timeout_error(self, mocker: MockerFixture) -> None:
        """Test that timeout errors are propagated."""
        mocker.patch(
            "pipelex.tools.misc.base64_utils.fetch_file_from_url_httpx",
            side_effect=httpx.TimeoutException("Request timed out"),
        )

        with pytest.raises(httpx.TimeoutException):
            await make_base64_url_from_http_url(url="https://slow.example.com/image.png")

    @pytest.mark.parametrize(
        ("topic", "file_path", "expected_mime_prefix"),
        [
            ("png", ImageTestCases.IMAGE_FILE_PATH_PNG_1, "data:image/png;base64,"),
            ("jpeg", ImageTestCases.IMAGE_FILE_PATH_JPG_1, "data:image/jpeg;base64,"),
        ],
    )
    async def test_detects_file_type_from_content(
        self,
        mocker: MockerFixture,
        topic: str,
        file_path: str,
        expected_mime_prefix: str,
    ) -> None:
        """Test that file type is correctly detected from content bytes, not URL."""
        with open(file_path, "rb") as file_handle:
            file_bytes = file_handle.read()

        # Mock with a misleading URL extension
        mocker.patch(
            "pipelex.tools.misc.base64_utils.fetch_file_from_url_httpx",
            return_value=file_bytes,
        )

        # URL says .txt but content is image - should detect from content
        result = await make_base64_url_from_http_url(url=f"https://example.com/file.txt?topic={topic}")

        assert result.startswith(expected_mime_prefix)
