from collections.abc import Generator
from contextlib import contextmanager

import httpx
from httpx import USE_CLIENT_DEFAULT, Timeout
from mthds.protocol.problem.registry import CoreCode

from pipelex.config import fetch_max_bytes, is_fetch_ssrf_guard_enabled
from pipelex.tools.misc.bounded_body_decoder import ACCEPTED_CONTENT_CODINGS, BoundedBodyDecoder, content_coding_of
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


def _declared_length_of(*, response: httpx.Response) -> int | None:
    """The body length the response declares, or ``None`` when it declares none or one that does not parse."""
    content_length = response.headers.get("content-length")
    if content_length is None:
        return None
    try:
        return int(content_length)
    except ValueError:
        return None


async def _send_following_redirects(*, client: httpx.AsyncClient, request: httpx.Request) -> httpx.Response:
    """Send ``request`` and follow its redirects by hand, closing each hop's response without reading its body.

    httpx following the redirects itself reads every hop's body whole, uncapped, so a redirect answered with a huge or
    compressed body would get past the cap. Each hop is still sent through the client's transport, so the SSRF guard
    vets it, and the next request is the one httpx builds, with its method rewrite and its cross-origin header stripping.

    Returns:
        The final response, streamed and unread, which the caller closes.

    Raises:
        httpx.TooManyRedirects: The chain is longer than the client's ``max_redirects``.
    """
    redirect_count = 0
    while True:
        response = await client.send(request, stream=True, follow_redirects=False)
        next_request = response.next_request
        if next_request is None:
            return response
        await response.aclose()
        redirect_count += 1
        if redirect_count > client.max_redirects:
            msg = "Exceeded maximum allowed redirects."
            raise httpx.TooManyRedirects(msg, request=next_request)
        request = next_request


async def fetch_file_and_content_type_from_url_httpx(
    url: str,
    *,
    max_bytes: int | None = None,
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

    The body is read as a stream under a byte cap, so that a URL serving more than the runtime
    will hold cannot exhaust its memory. Redirects are followed without reading their bodies.
    A response whose ``Content-Length`` already passes its bound is refused before any of its
    body is read: the cap for an uncompressed body, the compressed bound for a compressed one.
    A body is counted once decoded, by a decoder that never returns more than the cap allows,
    so a compressed body is refused for what it expands to, one byte past the cap, and its raw
    bytes are bounded too (:class:`BoundedBodyDecoder`). Only ``gzip`` and ``deflate`` are asked
    for and read; any other content coding, or more than one, is refused, and so is a
    compressed body that is truncated or carries trailing data other than NUL padding after a
    gzip member.

    Args:
        url: The http(s) URL to fetch.
        max_bytes: A tighter limit of the caller's own, in bytes. The cap is the smaller of it and
            ``runtime.network.max_fetch_bytes``, which alone applies when it is ``None``: a caller
            can tighten the cap, never loosen it, and there is no uncapped fetch.
        request_timeout: Seconds allowed for each phase of the request, or ``None`` for
            httpx's default.
        transport: A test seam, for a ``MockTransport``. Production code never passes it:
            passing one replaces the guard.

    Returns:
        The response body, and the declared media type or ``None``.

    Raises:
        RemoteFileTooLargeError: The body, as declared or as read, is past the cap, or its
            compressed bytes past the compressed bound, which its ``bound`` names. It is a
            ``RemoteFileFetchError``, so every catch site of a failed download catches it.
        RemoteFileFetchError: The server answered with an error status, refused the
            connection, did not answer in time, redirected too many times, or answered in a
            content coding the runtime does not read or a compressed body that does not decode,
            or the URL does not parse.
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
    limit = fetch_max_bytes() if max_bytes is None else min(max_bytes, fetch_max_bytes())
    raw_bytes: bytes
    declared_content_type: str | None
    try:
        async with httpx.AsyncClient(headers={"User-Agent": user_agent, "Accept-Encoding": ACCEPTED_CONTENT_CODINGS}, transport=transport) as client:
            # Built here, where the timeout is chosen: every redirect request httpx builds from it keeps its timeout.
            request = client.build_request("GET", url, timeout=timeout)
            response = await _send_following_redirects(client=client, request=request)
            # Closing the response leaves the rest of a body cut off here unread.
            try:
                response.raise_for_status()
                decoder = BoundedBodyDecoder(coding=content_coding_of(headers=response.headers), limit=limit)
                declared_length = _declared_length_of(response=response)
                if declared_length is not None:
                    decoder.refuse_declared_length_past_bound(declared_length=declared_length)
                async for raw_chunk in response.aiter_raw():
                    decoder.feed(chunk=raw_chunk)
                raw_bytes = decoder.finish()
                declared_content_type = response.headers.get("content-type")
            finally:
                await response.aclose()
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

    if declared_content_type is None:
        return raw_bytes, None
    media_type = declared_content_type.split(";")[0].strip().lower()
    return raw_bytes, media_type or None


async def fetch_file_from_url_httpx(
    url: str,
    *,
    max_bytes: int | None = None,
    request_timeout: int | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bytes:
    """Fetch the bytes at ``url``, or raise :class:`RemoteFileFetchError` saying why not.

    Guarded against private destinations and read under a byte cap, which ``max_bytes`` may
    tighten but never loosen, like
    :func:`fetch_file_and_content_type_from_url_httpx`, whose ``max_bytes`` and ``transport``
    test seam it forwards.

    Raises:
        RemoteFileTooLargeError: The body, as declared or as read, is past the cap.
        RemoteFileFetchError: The server answered with an error status, refused the
            connection, or did not answer in time.
        SsrfBlockedError: The destination, or a redirect hop's, is not a globally routable
            address.
    """
    raw_bytes, _ = await fetch_file_and_content_type_from_url_httpx(
        url,
        max_bytes=max_bytes,
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
