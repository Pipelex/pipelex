import base64

import aiofiles

from pipelex.tools.misc.file_fetch_utils import fetch_file_from_url_httpx
from pipelex.tools.misc.file_utils import load_binary_async
from pipelex.tools.misc.filetype_utils import FileType, detect_file_type_from_bytes


async def load_binary_as_base64(path: str) -> str:
    """Load a file and return its contents as a base64-encoded string."""
    async with aiofiles.open(path, "rb") as fp:  # pyright: ignore[reportUnknownMemberType]
        data_bytes = await fp.read()
        return base64.b64encode(data_bytes).decode("ascii")


async def make_base64_url_from_path(path: str) -> str:
    """Create a data: URL from a local file path."""
    raw_bytes = await load_binary_async(path=path)
    base64_data = base64.b64encode(raw_bytes).decode("ascii")
    file_type = detect_file_type_from_bytes(raw_bytes=raw_bytes)
    return make_base64_url(base64_data=base64_data, file_type=file_type)


async def make_base64_url_from_http_url(url: str) -> str:
    """Fetch a URL and create a data: URL from its contents."""
    raw_bytes = await fetch_file_from_url_httpx(url=url)
    base64_data = base64.b64encode(raw_bytes).decode("ascii")
    file_type = detect_file_type_from_bytes(raw_bytes=raw_bytes)
    return make_base64_url(base64_data=base64_data, file_type=file_type)


def make_base64_url(
    base64_data: str,
    file_type: FileType,
) -> str:
    """Create a data: URL from base64 string and file type."""
    return f"data:{file_type.mime};base64,{base64_data}"


def is_prefixed_base64_url(possibly_base64_url: str) -> bool:
    return possibly_base64_url.startswith("data:") and ";base64," in possibly_base64_url


def strip_base64_str_if_needed(base64_str: str) -> str:
    if "," in base64_str:
        return base64_str.split(",", 1)[1]
    if "data:" in base64_str and ";base64," in base64_str:
        return base64_str.split(";base64,", 1)[1]
    return base64_str


def extract_base64_str_from_base64_url_if_possible(possibly_base64_url: str) -> tuple[str, str] | None:
    if not possibly_base64_url.startswith("data:"):
        return None
    if ";base64," not in possibly_base64_url:
        return None
    mime_type = possibly_base64_url[5:].split(";base64,", 1)[0]
    base64_str = possibly_base64_url.split(";base64,", 1)[1]
    return base64_str, mime_type
