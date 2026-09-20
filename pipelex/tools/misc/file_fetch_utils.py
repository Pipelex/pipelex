import httpx
from httpx import Response

from pipelex.tools.misc.exceptions import RemoteFileFetchError
from pipelex.tools.misc.http_utils import get_user_agent


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

    Returns:
        The response body, and the declared media type or ``None``.

    Raises:
        RemoteFileFetchError: The server answered with an error status, refused the
            connection, or did not answer in time.
    """
    user_agent = get_user_agent()
    try:
        async with httpx.AsyncClient(headers={"User-Agent": user_agent}, transport=transport) as client:
            response: Response = await client.get(
                url,
                timeout=request_timeout,
                follow_redirects=True,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        msg = f"Could not fetch '{url}': the server answered HTTP {exc.response.status_code}"
        raise RemoteFileFetchError(msg) from exc
    except httpx.TimeoutException as exc:
        msg = f"Could not fetch '{url}': the request timed out"
        raise RemoteFileFetchError(msg) from exc
    except httpx.ConnectError as exc:
        msg = f"Could not fetch '{url}': the host could not be reached"
        raise RemoteFileFetchError(msg) from exc
    except httpx.RequestError as exc:
        msg = f"Could not fetch '{url}': the request failed ({type(exc).__name__})"
        raise RemoteFileFetchError(msg) from exc

    declared_content_type = response.headers.get("content-type")
    content_type = declared_content_type.split(";")[0].strip().lower() or None if declared_content_type else None
    return response.content, content_type


async def fetch_file_from_url_httpx(
    url: str,
    *,
    request_timeout: int | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bytes:
    """Fetch the bytes at ``url``, or raise :class:`RemoteFileFetchError` saying why not.

    Raises:
        RemoteFileFetchError: The server answered with an error status, refused the
            connection, or did not answer in time.
    """
    raw_bytes, _ = await fetch_file_and_content_type_from_url_httpx(
        url,
        request_timeout=request_timeout,
        transport=transport,
    )
    return raw_bytes
