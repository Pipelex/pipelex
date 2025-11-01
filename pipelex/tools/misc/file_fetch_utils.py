import httpx
from httpx import Response

from pipelex.tools.misc.http_utils import get_user_agent


async def fetch_file_from_url_httpx_async(
    url: str,
    request_timeout: int | None = None,
) -> bytes:
    user_agent = get_user_agent()
    async with httpx.AsyncClient(headers={"User-Agent": user_agent}) as client:
        response: Response = await client.get(
            url,
            timeout=request_timeout,
            follow_redirects=True,
        )
        response.raise_for_status()  # Raise exception for 4XX/5XX status codes

        return response.content


def fetch_file_from_url_httpx(
    url: str,
    request_timeout: int | None = None,
) -> bytes:
    user_agent = get_user_agent()
    with httpx.Client(headers={"User-Agent": user_agent}) as client:
        response: Response = client.get(
            url,
            timeout=request_timeout,
            follow_redirects=True,
        )
        response.raise_for_status()  # Raise exception for 4XX/5XX status codes

        bytes_content: bytes = response.content
        return bytes_content
