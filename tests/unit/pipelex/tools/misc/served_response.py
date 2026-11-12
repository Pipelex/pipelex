import httpx


def served_response(*, status_code: int = 200, content: bytes = b"", headers: dict[str, str] | None = None) -> httpx.Response:
    """A response as a real transport hands it over, its body still to be streamed and its length declared.

    ``httpx.Response(content=...)`` reads and decodes its body as it is built, which no transport does, so a fetch that
    streams the raw body could never read it.
    """
    served_headers = {"Content-Length": str(len(content)), **(headers or {})}
    return httpx.Response(status_code, headers=served_headers, stream=httpx.ByteStream(content))
