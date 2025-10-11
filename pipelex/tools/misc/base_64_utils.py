import asyncio
import base64

import aiofiles

from pipelex.tools.misc.file_utils import save_bytes_to_binary_file


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


def save_base64_to_binary_file(
    b64: str,
    file_path: str,
):
    # Ensure we're getting clean base64 data without any prefixes
    base64_str = b64
    # Remove potential data URL prefix if present
    if "," in base64_str:
        base64_str = base64_str.split(",", 1)[1]
    if "data:" in base64_str and ";base64," in base64_str:
        base64_str = base64_str.split(";base64,", 1)[1]

    # Decode base64
    byte_data = base64.b64decode(base64_str)

    save_bytes_to_binary_file(file_path=file_path, byte_data=byte_data)
