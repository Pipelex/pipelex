from collections.abc import Generator
from contextlib import contextmanager

import httpx
from httpx import USE_CLIENT_DEFAULT, Response, Timeout
from mthds.protocol.problem.registry import CoreCode

from pipelex.config import is_fetch_ssrf_guard_enabled
from pipelex.tools.misc.exceptions import RemoteFileFetchError
from pipelex.tools.misc.http_utils import get_user_agent
from pipelex.tools.network.ssrf_guard import SsrfGuardedTransport

# The statuses by which a server that is there says it cannot answer now, besides every 5xx: a retry may get the file.
_TRANSIENT_HTTP_STATUSES = frozenset({408, 425, 429})
_HTTP_SERVER_ERROR_FLOOR = 500


def _host_of(*, url: str) -> str | None:
    """The host the URL names, or ``None`` when it names none or does not parse, which the request then reports."""
    try:
        return httpx.URL(url).host or None
    except httpx.InvalidURL:
        return None


async def fetch_file_and_content_type_from_url_httpx(
    url: str,
    *,
    request_timeout: int | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[bytes, str | None]:
    """Fetch the bytes at ``url`` along with the media type the server declared for them.

    The content type is the response's own ``Content-Type`` with its parameters stripped
    and lowercased, or ``None`` when the server declared none. It is the only honest
    answer about what a remote URL actually serves, so a caller that stores those bytes
    under a media type has to ask for it rather than guess from what it requested.

    The URL is whatever a value carried, so a method can aim it anywhere. Unless the
    ``runtime.network.is_fetch_ssrf_guard_enabled`` switch is off, the request goes through
    :class:`SsrfGuardedTransport`, which refuses a private, loopback, link-local or
    metadata destination at connect time, on the first request and on every redirect hop.
    The guard dials directly, so ``HTTP_PROXY`` / ``HTTPS_PROXY`` are honoured only with the
    switch off.

    Args:
        url: The http(s) URL to fetch.
        request_timeout: Seconds allowed for each phase of the request, or ``None`` for
            httpx's default.
        transport: A test seam, for a ``MockTransport``. Production code never passes it:
            passing one replaces the guard.

    Returns:
        The response body, and the declared media type or ``None``.

    Raises:
        RemoteFileFetchError: The server answered with an error status, refused the
            connection, or did not answer in time, or the URL does not parse.
        SsrfBlockedError: The destination, or a redirect hop's, is not a globally routable
            address. It is a security error and deliberately not a ``RemoteFileFetchError``,
            so no caller's fallback for a failed download absorbs it.
    """
    if transport is None and is_fetch_ssrf_guard_enabled():
        transport = SsrfGuardedTransport()
    user_agent = get_user_agent()
    # httpx reads an explicit `timeout=None` as NO timeout, not as "use the client's
    # default" — that is what its `USE_CLIENT_DEFAULT` sentinel is for. Passing the
    # bare `None` this signature defaults to left a hanging server able to block a
    # caller forever, and the `TimeoutException` branch below unreachable.
    timeout = Timeout(request_timeout) if request_timeout is not None else USE_CLIENT_DEFAULT
    # No message names the URL, which is the value an input or a pipe carried, a signed link's credential included: it
    # says what the server or the network answered. The URL's host is a fact the error holds, read once here, so that
    # the code that invites a retry, `input.url_unreachable`, takes it as its declared `host` parameter, and a code a
    # catch site chooses instead, which does not declare it, is given nothing it would refuse.
    host = _host_of(url=url)
    try:
        async with httpx.AsyncClient(headers={"User-Agent": user_agent}, transport=transport) as client:
            response: Response = await client.get(
                url,
                timeout=timeout,
                follow_redirects=True,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        reason = f"the server answered HTTP {status_code}"
        msg = f"Could not fetch a remote file: {reason}"
        if status_code in _TRANSIENT_HTTP_STATUSES or status_code >= _HTTP_SERVER_ERROR_FLOOR:
            # The server is there but cannot answer now: a retry may get the file.
            raise RemoteFileFetchError(msg, host=host).with_error_code(CoreCode.INPUT_URL_UNREACHABLE) from exc
        raise RemoteFileFetchError(msg, host=host, reason=reason) from exc
    except httpx.TimeoutException as exc:
        msg = "Could not fetch a remote file: the request timed out"
        raise RemoteFileFetchError(msg, host=host).with_error_code(CoreCode.INPUT_URL_UNREACHABLE) from exc
    except httpx.ConnectError as exc:
        msg = "Could not fetch a remote file: the host could not be reached"
        raise RemoteFileFetchError(msg, host=host).with_error_code(CoreCode.INPUT_URL_UNREACHABLE) from exc
    except httpx.RequestError as exc:
        reason = f"the request failed ({type(exc).__name__})"
        msg = f"Could not fetch a remote file: {reason}"
        raise RemoteFileFetchError(msg, host=host, reason=reason) from exc
    except httpx.InvalidURL as exc:
        # Raised while the request is built, before anything is sent, and not a `RequestError`: its text quotes the
        # part of the URL the parser refused, so it is named by what failed alone.
        reason = "the URL does not parse"
        msg = f"Could not fetch a remote file: {reason}"
        raise RemoteFileFetchError(msg, reason=reason) from exc

    declared_content_type: str | None = response.headers.get("content-type")
    if declared_content_type is None:
        return response.content, None
    media_type = declared_content_type.split(";")[0].strip().lower()
    return response.content, media_type or None


async def fetch_file_from_url_httpx(
    url: str,
    *,
    request_timeout: int | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bytes:
    """Fetch the bytes at ``url``, or raise :class:`RemoteFileFetchError` saying why not.

    Guarded against private destinations like
    :func:`fetch_file_and_content_type_from_url_httpx`, whose ``transport`` test seam it forwards.

    Raises:
        RemoteFileFetchError: The server answered with an error status, refused the
            connection, or did not answer in time.
        SsrfBlockedError: The destination, or a redirect hop's, is not a globally routable
            address.
    """
    raw_bytes, _ = await fetch_file_and_content_type_from_url_httpx(
        url,
        request_timeout=request_timeout,
        transport=transport,
    )
    return raw_bytes


@contextmanager
def fetching_for_input(*, input_name: str | None) -> Generator[None]:
    """Name ``input_name`` on a :class:`RemoteFileFetchError` the block raises, the input whose URL it fetched.

    A fetch knows the URL alone, which no message names, being the run's data; the caller that knows which input the URL
    belongs to wraps the fetch, so that a pipe reading several files says which one failed. An error that already names
    an input keeps it, and ``None``, a URL no input gave, names nothing.

    Raises:
        RemoteFileFetchError: What the block raised, naming the input.
    """
    try:
        yield
    except RemoteFileFetchError as exc:
        if input_name is not None and exc.input_name is None:
            exc.with_input(input_name=input_name)
        raise
