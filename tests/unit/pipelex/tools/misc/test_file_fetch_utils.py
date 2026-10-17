import httpx
import pytest
from mthds.protocol.problem.registry import CoreCode, ProblemDomain

from pipelex.errors.error_codes import error_code_spec
from pipelex.errors.problem import ProblemView
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

    @pytest.mark.parametrize(
        ("status_code", "expected_code"),
        [
            (404, CoreCode.INPUT_FILE_UNREADABLE),
            (403, CoreCode.INPUT_FILE_UNREADABLE),
            (429, CoreCode.INPUT_URL_UNREACHABLE),
            (500, CoreCode.INPUT_URL_UNREACHABLE),
            (503, CoreCode.INPUT_URL_UNREACHABLE),
        ],
    )
    async def test_error_status_raises_an_input_error(self, status_code: int, expected_code: CoreCode) -> None:
        """A 4xx/5xx becomes an input error, whose message names the URL and the status.

        A server that will not serve the file is ``input.file_unreadable``; one that cannot answer now, a 5xx or a
        429, is ``input.url_unreachable``, which a retry may get past.
        """
        with pytest.raises(RemoteFileFetchError) as exc_info:
            await fetch_file_from_url_httpx(url=URL, transport=_transport_answering(status_code))

        assert exc_info.value.resolve_error_code() == expected_code
        caller = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert caller.code == expected_code
        assert caller.domain == ProblemDomain.INPUT
        assert caller.is_retryable is error_code_spec(expected_code).invites_retry
        operator = exc_info.value.to_problem(view=ProblemView.OPERATOR)
        assert operator.diagnostics is not None
        assert f"HTTP {status_code}" in operator.diagnostics.message
        assert URL in operator.diagnostics.message

    @pytest.mark.parametrize(
        ("exc", "expected", "expected_code"),
        [
            pytest.param(httpx.ConnectError("boom"), "could not be reached", CoreCode.INPUT_URL_UNREACHABLE, id="connect"),
            pytest.param(httpx.ReadTimeout("slow"), "timed out", CoreCode.INPUT_URL_UNREACHABLE, id="timeout"),
            pytest.param(httpx.RemoteProtocolError("bad"), "request failed", CoreCode.INPUT_FILE_UNREADABLE, id="protocol"),
        ],
    )
    async def test_network_failure_raises_an_input_error(self, exc: httpx.RequestError, expected: str, expected_code: CoreCode) -> None:
        with pytest.raises(RemoteFileFetchError, match=expected) as exc_info:
            await fetch_file_from_url_httpx(url=URL, transport=_transport_raising(exc))
        assert exc_info.value.resolve_error_code() == expected_code


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
