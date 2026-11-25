import base64
from pathlib import Path

from pipelex.tools.misc.file_utils import load_binary_async
from pipelex.tools.misc.filetype_utils import FileType, detect_file_type_from_bytes
from pipelex.tools.uri.data_url import is_data_url, parse_data_url


async def load_binary_as_base64(path: Path) -> str:
    """Load a file and return its contents as a base64-encoded string."""
    data_bytes = await load_binary_async(path=path)
    return base64.b64encode(data_bytes).decode("ascii")


async def make_base64_url_from_path(path: Path) -> str:
    """Create a data: URL from a local file path."""
    raw_bytes = await load_binary_async(path=path)
    base64_data = base64.b64encode(raw_bytes).decode("ascii")
    file_type = detect_file_type_from_bytes(raw_bytes=raw_bytes)
    return make_base64_url(base64_data=base64_data, file_type=file_type)


def make_base64_url_from_bytes(raw_bytes: bytes) -> str:
    """Create a data: URL from raw bytes, detecting file type automatically."""
    base64_data = base64.b64encode(raw_bytes).decode("ascii")
    file_type = detect_file_type_from_bytes(raw_bytes=raw_bytes)
    return make_base64_url(base64_data=base64_data, file_type=file_type)


def make_base64_url(
    base64_data: str,
    *,
    file_type: FileType,
) -> str:
    """Create a data: URL from base64 string and file type."""
    return f"data:{file_type.mime};base64,{base64_data}"


def is_prefixed_base64_url(possibly_base64_url: str) -> bool:
    """Whether the value is a base64 `data:` URL, its header read up to its first comma (`parse_data_url`)."""
    if not is_data_url(uri=possibly_base64_url) or "," not in possibly_base64_url:
        return False
    return parse_data_url(uri=possibly_base64_url).is_base64


def strip_base64_str_if_needed(base64_str: str) -> str:
    """The base64 text of a value that may carry a data URL's header: everything after its first comma, else the value."""
    if "," not in base64_str:
        return base64_str
    if is_data_url(uri=base64_str):
        return parse_data_url(uri=base64_str).payload
    # A header without its scheme, such as `image/png;base64,…`, ends at its first comma too.
    return base64_str.split(",", 1)[1]


def extract_base64_str_from_base64_url_if_possible(possibly_base64_url: str) -> tuple[str, str] | None:
    """The payload and the declared media type of a base64 `data:` URL, or `None` for any other value."""
    if not is_prefixed_base64_url(possibly_base64_url):
        return None
    parsed = parse_data_url(uri=possibly_base64_url)
    return parsed.payload, parsed.media_type
