import httpx
from httpx import Response

from pipelex.tools.misc.exceptions import RemoteFileFetchError
from pipelex.tools.misc.http_utils import get_user_agent


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

    return response.content
