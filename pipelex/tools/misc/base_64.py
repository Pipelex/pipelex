# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import asyncio
import base64

import aiofiles


def load_binary_as_base64(path: str) -> bytes:
    with open(path, "rb") as image_file:
        return base64.b64encode(image_file.read())


async def load_binary_as_base64_async(path: str) -> bytes:
    async with aiofiles.open(path, "rb") as fp:  # type: ignore[reportUnknownMemberType]
        data_bytes = await fp.read()
        return base64.b64encode(data_bytes)


def encode_to_base64(data_bytes: bytes) -> bytes:
    b64 = base64.b64encode(data_bytes)
    return b64


async def encode_to_base64_async(data_bytes: bytes) -> bytes:
    # Use asyncio.to_thread to run the CPU-bound task in a separate thread
    b64 = await asyncio.to_thread(base64.b64encode, data_bytes)
    return b64
