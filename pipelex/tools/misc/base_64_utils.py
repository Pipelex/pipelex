import asyncio
import base64

import aiofiles

from pipelex.tools.misc.file_utils import save_bytes_to_binary_file
from pipelex.tools.misc.filetype_utils import detect_file_type_from_base64


def load_binary_as_base64(path: str) -> bytes:
    with open(path, "rb") as fp:
        return base64.b64encode(fp.read())


async def load_binary_as_base64_async(path: str) -> bytes:
    async with aiofiles.open(path, "rb") as fp:  # pyright: ignore[reportUnknownMemberType]
        data_bytes = await fp.read()
        return base64.b64encode(data_bytes)


async def load_binary_async(path: str) -> bytes:
    async with aiofiles.open(path, "rb") as fp:  # pyright: ignore[reportUnknownMemberType]
        return await fp.read()


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
