import httpx
import pytest

from pipelex.base_exceptions import DisclosureMode
from pipelex.tools.misc.exceptions import RemoteFileFetchError
from pipelex.tools.misc.file_fetch_utils import fetch_file_from_url_httpx

URL = "https://example.com/file.pdf"


def _transport_answering(status_code: int, content: bytes = b"") -> httpx.MockTransport:
    return httpx.MockTransport(lambda _request: httpx.Response(status_code, content=content))


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
