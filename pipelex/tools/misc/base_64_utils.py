import asyncio
import base64

import aiofiles

from pipelex.tools.misc.file_fetch_utils import fetch_file_from_url_httpx_async
from pipelex.tools.misc.file_utils import load_binary, load_binary_async, save_bytes_to_binary_file
from pipelex.tools.misc.filetype_utils import FileType, detect_file_type_from_base64, detect_file_type_from_bytes
from pipelex.tools.misc.path_utils import clarify_path_or_url


def load_binary_as_base64(path: str) -> bytes:
    with open(path, "rb") as file_pointer:
        return base64.b64encode(file_pointer.read())


async def load_binary_as_base64_async(path: str) -> bytes:
    async with aiofiles.open(path, "rb") as fp:  # pyright: ignore[reportUnknownMemberType]
        data_bytes = await fp.read()
        return base64.b64encode(data_bytes)


def make_base_64_url_from_path(path: str) -> str:
    raw_bytes = load_binary(path=path)
    base_64 = base64.b64encode(raw_bytes)
    file_type = detect_file_type_from_bytes(buf=raw_bytes)
    return make_base_64_url(base_64=base_64, file_type=file_type)


async def make_base_64_url_from_path_async(path: str) -> str:
    raw_bytes = await load_binary_async(path=path)
    base_64 = base64.b64encode(raw_bytes)
    file_type = detect_file_type_from_bytes(buf=raw_bytes)
    return make_base_64_url(base_64=base_64, file_type=file_type)


async def make_base_64_url_from_url_async(url: str) -> str:
    raw_bytes = await fetch_file_from_url_httpx_async(url=url)
    base_64 = base64.b64encode(raw_bytes)
    file_type = detect_file_type_from_bytes(buf=raw_bytes)
    return make_base_64_url(base_64=base_64, file_type=file_type)


async def make_base_64_url_from_location_async(location: str) -> str:
    pdf_path, pdf_url = clarify_path_or_url(path_or_uri=location)
    if pdf_url:
        base_64_url = await make_base_64_url_from_url_async(url=pdf_url)
    else:  # pdf_path must be provided based on validation
        assert pdf_path is not None
        base_64_url = await make_base_64_url_from_path_async(path=pdf_path)
    return base_64_url


def make_base_64_url(
    base_64: bytes,
    file_type: FileType,
) -> str:
    return f"data:{file_type.mime};base64,{base_64.decode('utf-8')}"


def encode_to_base64(data_bytes: bytes) -> bytes:
    return base64.b64encode(data_bytes)


async def encode_to_base64_async(data_bytes: bytes) -> bytes:
    # Use asyncio.to_thread to run the CPU-bound task in a separate thread
    return await asyncio.to_thread(base64.b64encode, data_bytes)


def strip_base_64_str_if_needed(base64_str: str) -> str:
    if "," in base64_str:
        return base64_str.split(",", 1)[1]
    if "data:" in base64_str and ";base64," in base64_str:
        return base64_str.split(";base64,", 1)[1]
    return base64_str


def is_prefixed_base64_url(possibly_base64_url: str) -> bool:
    return possibly_base64_url.startswith("data:") and ";base64," in possibly_base64_url


def extract_base_64_str_from_base64_url_if_possible(possibly_base64_url: str) -> tuple[str, str] | None:
    if not possibly_base64_url.startswith("data:"):
        return None
    if ";base64," not in possibly_base64_url:
        return None
    mime_type = possibly_base64_url[5:].split(";base64,", 1)[0]
    base64_str = possibly_base64_url.split(";base64,", 1)[1]
    return base64_str, mime_type


def prefixed_base64_str_from_base64_bytes(b64_bytes: bytes) -> str:
    file_type = detect_file_type_from_base64(b64_bytes)
    return f"data:{file_type.mime};base64,{base64.b64encode(b64_bytes).decode('utf-8')}"


def prefixed_base64_str_from_base64_str(b64_str: str) -> str:
    """Create a data URL from an already base64-encoded string.

    Args:
        b64_str: Base64-encoded string (without data URL prefix)

    Returns:
        Data URL string: data:{mime};base64,{b64_str}
    """
    file_type = detect_file_type_from_base64(b64_str)
    return f"data:{file_type.mime};base64,{b64_str}"


def save_base_64_str_to_binary_file(
    base_64_str: str,
    file_path: str,
):
    stripped_base_64_str = strip_base_64_str_if_needed(base_64_str)

    # Decode base64
    byte_data = base64.b64decode(stripped_base_64_str)

    save_bytes_to_binary_file(file_path=file_path, byte_data=byte_data)
