import httpx
import pytest
from pytest_mock import MockerFixture

from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME
from pipelex.tools.uri.uri_resolver import make_base64_url_from_any_uri


@pytest.mark.asyncio(loop_scope="class")
class TestUriResolverErrorHandling:
    """Tests for error handling in URI resolver functions."""

    async def test_http_404_error_propagates(self, mocker: MockerFixture) -> None:
        """Test that HTTP 404 errors are propagated through make_base64_url_from_any_uri."""
        mocker.patch(
            "pipelex.tools.misc.base64_utils.fetch_file_from_url_httpx",
            side_effect=httpx.HTTPStatusError(
                message="404 Not Found",
                request=httpx.Request("GET", "https://example.com/not-found.png"),
                response=httpx.Response(404),
            ),
        )

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await make_base64_url_from_any_uri("https://example.com/not-found.png")

        assert exc_info.value.response.status_code == 404

    async def test_http_500_error_propagates(self, mocker: MockerFixture) -> None:
        """Test that HTTP 500 errors are propagated through make_base64_url_from_any_uri."""
        mocker.patch(
            "pipelex.tools.misc.base64_utils.fetch_file_from_url_httpx",
            side_effect=httpx.HTTPStatusError(
                message="500 Internal Server Error",
                request=httpx.Request("GET", "https://example.com/error"),
                response=httpx.Response(500),
            ),
        )

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await make_base64_url_from_any_uri("https://example.com/error")

        assert exc_info.value.response.status_code == 500

    async def test_http_403_forbidden_error_propagates(self, mocker: MockerFixture) -> None:
        """Test that HTTP 403 Forbidden errors are propagated."""
        mocker.patch(
            "pipelex.tools.misc.base64_utils.fetch_file_from_url_httpx",
            side_effect=httpx.HTTPStatusError(
                message="403 Forbidden",
                request=httpx.Request("GET", "https://example.com/forbidden.png"),
                response=httpx.Response(403),
            ),
        )

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await make_base64_url_from_any_uri("https://example.com/forbidden.png")

        assert exc_info.value.response.status_code == 403

    async def test_connection_error_propagates(self, mocker: MockerFixture) -> None:
        """Test that connection errors are propagated."""
        mocker.patch(
            "pipelex.tools.misc.base64_utils.fetch_file_from_url_httpx",
            side_effect=httpx.ConnectError("Connection refused"),
        )

        with pytest.raises(httpx.ConnectError):
            await make_base64_url_from_any_uri("https://unreachable.example.com/image.png")

    async def test_timeout_error_propagates(self, mocker: MockerFixture) -> None:
        """Test that timeout errors are propagated."""
        mocker.patch(
            "pipelex.tools.misc.base64_utils.fetch_file_from_url_httpx",
            side_effect=httpx.TimeoutException("Request timed out"),
        )

        with pytest.raises(httpx.TimeoutException):
            await make_base64_url_from_any_uri("https://slow.example.com/image.png")

    async def test_dns_error_propagates(self, mocker: MockerFixture) -> None:
        """Test that DNS resolution errors are propagated."""
        mocker.patch(
            "pipelex.tools.misc.base64_utils.fetch_file_from_url_httpx",
            side_effect=httpx.ConnectError("DNS resolution failed"),
        )

        with pytest.raises(httpx.ConnectError):
            await make_base64_url_from_any_uri("https://nonexistent-domain-12345.com/image.png")

    async def test_pipelex_storage_propagates_storage_errors(self, mocker: MockerFixture) -> None:
        """Test that storage errors are propagated when loading pipelex-storage:// URIs."""
        from pipelex.tools.storage.exceptions import StorageFileNotFoundError  # noqa: PLC0415

        mock_storage = mocker.AsyncMock()
        mock_storage.load = mocker.AsyncMock(side_effect=StorageFileNotFoundError("Key not found"))

        storage_uri = f"{PIPELEX_STORAGE_SCHEME}bucket/path/file.png"

        with pytest.raises(StorageFileNotFoundError):
            await make_base64_url_from_any_uri(storage_uri, storage_provider=mock_storage)

    async def test_local_file_not_found_raises_file_not_found_error(self) -> None:
        """Test that non-existent local files raise FileNotFoundError."""
        non_existent_path = "/path/to/non/existent/file.png"

        with pytest.raises(FileNotFoundError):
            await make_base64_url_from_any_uri(non_existent_path)

    async def test_local_file_permission_denied_raises_permission_error(self, mocker: MockerFixture) -> None:
        """Test that permission errors for local files are propagated."""
        mocker.patch(
            "pipelex.tools.misc.base64_utils.load_binary_async",
            side_effect=PermissionError("Permission denied"),
        )

        with pytest.raises(PermissionError):
            await make_base64_url_from_any_uri("/restricted/file.png")

    async def test_ssl_certificate_error_propagates(self, mocker: MockerFixture) -> None:
        """Test that SSL certificate errors are propagated."""
        mocker.patch(
            "pipelex.tools.misc.base64_utils.fetch_file_from_url_httpx",
            side_effect=httpx.ConnectError("SSL certificate verification failed"),
        )

        with pytest.raises(httpx.ConnectError):
            await make_base64_url_from_any_uri("https://expired-cert.example.com/image.png")

    @pytest.mark.parametrize(
        ("topic", "status_code"),
        [
            ("bad_request", 400),
            ("unauthorized", 401),
            ("payment_required", 402),
            ("not_found", 404),
            ("method_not_allowed", 405),
            ("gone", 410),
            ("internal_server_error", 500),
            ("bad_gateway", 502),
            ("service_unavailable", 503),
            ("gateway_timeout", 504),
        ],
    )
    async def test_various_http_status_codes_propagate(
        self,
        mocker: MockerFixture,
        topic: str,
        status_code: int,
    ) -> None:
        """Test that various HTTP status codes are properly propagated."""
        mocker.patch(
            "pipelex.tools.misc.base64_utils.fetch_file_from_url_httpx",
            side_effect=httpx.HTTPStatusError(
                message=f"{status_code} {topic}",
                request=httpx.Request("GET", f"https://example.com/{topic}"),
                response=httpx.Response(status_code),
            ),
        )

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await make_base64_url_from_any_uri(f"https://example.com/{topic}")

        assert exc_info.value.response.status_code == status_code
