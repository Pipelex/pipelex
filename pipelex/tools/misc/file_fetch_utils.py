import httpx
from httpx import Response


async def fetch_file_from_url_httpx_async(
    url: str,
    request_timeout: int | None = None,
) -> bytes:
    async with httpx.AsyncClient() as client:
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
    with httpx.Client() as client:
        response: Response = client.get(
            url,
            timeout=request_timeout,
            follow_redirects=True,
        )
        response.raise_for_status()  # Raise exception for 4XX/5XX status codes

        bytes_content: bytes = response.content
        return bytes_content
