import httpx
import pytest

from pipelex.base_exceptions import DisclosureMode
from pipelex.tools.misc.exceptions import RemoteFileFetchError
from pipelex.tools.misc.file_fetch_utils import fetch_file_and_content_type_from_url_httpx, fetch_file_from_url_httpx

URL = "https://example.com/file.pdf"


def _transport_answering(status_code: int, content: bytes = b"", headers: dict[str, str] | None = None) -> httpx.MockTransport:
    return httpx.MockTransport(lambda _request: httpx.Response(status_code, content=content, headers=headers))


def _transport_raising(exc: httpx.RequestError) -> httpx.MockTransport:
    def _handler(_request: httpx.Request) -> httpx.Response:
        raise exc

    return httpx.MockTransport(_handler)


@pytest.mark.asyncio(loop_scope="class")
class TestFetchFileFromUrl:
    async def test_success_returns_the_bytes(self) -> None:
        raw_bytes = await fetch_file_from_url_httpx(url=URL, transport=_transport_answering(200, b"%PDF-1.4"))
        assert raw_bytes == b"%PDF-1.4"

    @pytest.mark.parametrize("status_code", [404, 403, 500])
    async def test_error_status_raises_caller_facing_error(self, status_code: int) -> None:
        """A 4xx/5xx becomes an INPUT-domain error naming the URL and the status, kept under STRICT disclosure."""
        with pytest.raises(RemoteFileFetchError) as exc_info:
            await fetch_file_from_url_httpx(url=URL, transport=_transport_answering(status_code))

        strict = exc_info.value.to_error_report().to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert f"HTTP {status_code}" in strict["message"]
        assert URL in strict["message"]

    @pytest.mark.parametrize(
        ("exc", "expected"),
        [
            pytest.param(httpx.ConnectError("boom"), "could not be reached", id="connect"),
            pytest.param(httpx.ReadTimeout("slow"), "timed out", id="timeout"),
            pytest.param(httpx.RemoteProtocolError("bad"), "request failed", id="protocol"),
        ],
    )
    async def test_network_failure_raises_caller_facing_error(self, exc: httpx.RequestError, expected: str) -> None:
        with pytest.raises(RemoteFileFetchError, match=expected):
            await fetch_file_from_url_httpx(url=URL, transport=_transport_raising(exc))


@pytest.mark.asyncio(loop_scope="class")
class TestFetchFileAndContentTypeFromUrl:
    """The declared media type, which is the only honest answer about what a URL serves."""

    @pytest.mark.parametrize(
        ("served", "expected"),
        [
            pytest.param("image/png", "image/png", id="plain"),
            pytest.param("image/png; charset=binary", "image/png", id="parameters-stripped"),
            pytest.param("  IMAGE/PNG ; q=1 ", "image/png", id="whitespace-and-case-normalized"),
            pytest.param(None, None, id="silent-server"),
        ],
    )
    async def test_the_declared_content_type_is_reported_normalized(self, served: str | None, expected: str | None) -> None:
        headers = {"Content-Type": served} if served is not None else {}
        raw_bytes, content_type = await fetch_file_and_content_type_from_url_httpx(
            URL,
            transport=_transport_answering(200, b"\x89PNG", headers=headers),
        )

        assert raw_bytes == b"\x89PNG"
        assert content_type == expected


@pytest.mark.asyncio(loop_scope="class")
class TestFetchTimeout:
    """The timeout that the caller-facing timeout error depends on actually being set."""

    @staticmethod
    def _transport_recording(seen: dict[str, object]) -> httpx.MockTransport:
        def _handler(request: httpx.Request) -> httpx.Response:
            seen["timeout"] = request.extensions.get("timeout")
            return httpx.Response(200, content=b"ok")

        return httpx.MockTransport(_handler)

    async def test_no_request_timeout_leaves_the_client_default_in_force(self) -> None:
        """An explicit `timeout=None` would mean NO timeout in httpx, which is not the intent."""
        seen: dict[str, object] = {}
        await fetch_file_from_url_httpx(url=URL, transport=self._transport_recording(seen))

        assert seen["timeout"] == {"connect": 5.0, "read": 5.0, "write": 5.0, "pool": 5.0}

    async def test_an_explicit_request_timeout_is_honoured(self) -> None:
        seen: dict[str, object] = {}
        await fetch_file_from_url_httpx(url=URL, request_timeout=30, transport=self._transport_recording(seen))

        assert seen["timeout"] == {"connect": 30, "read": 30, "write": 30, "pool": 30}
