# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import asyncio
import base64

import aiofiles


def load_image_as_base64_from_path(path: str) -> bytes:
    """
    Reads an image file and returns its contents as a base64 encoded bytes object.

    This function opens an image file in binary mode, reads its contents,
    and encodes them in base64 format, suitable for embedding in web applications
    or transmitting in text-based protocols.

    Args:
        path (str): The path to the image file to be encoded.

    Returns:
        bytes: The base64 encoded contents of the image file.

    Raises:
        FileNotFoundError: If the image file does not exist.
        IOError: If there are issues reading the file.
    """
    with open(path, "rb") as image_file:
        return base64.b64encode(image_file.read())


async def load_image_as_base64_from_path_async(path: str) -> bytes:
    """
    Asynchronously reads an image file and returns its contents as a base64 encoded bytes object.

    This function asynchronously opens an image file in binary mode, reads its contents,
    and encodes them in base64 format. It's suitable for non-blocking I/O operations in
    async applications.

    Args:
        path (str): The path to the image file to be encoded.

    Returns:
        bytes: The base64 encoded contents of the image file.

    Raises:
        FileNotFoundError: If the image file does not exist.
        IOError: If there are issues reading the file.
    """
    async with aiofiles.open(path, "rb") as image_file:
        image_data = await image_file.read()
        return base64.b64encode(image_data)


def load_image_as_base64_from_bytes(image_bytes: bytes) -> bytes:
    """
    Encodes a bytes object containing image data to base64 format.

    This function takes raw image bytes and converts them to base64 encoding,
    suitable for embedding in web applications or transmitting in text-based protocols.

    Args:
        image_bytes (bytes): The raw image data to be encoded.

    Returns:
        bytes: The base64 encoded image data.
    """
    image_b64 = base64.b64encode(image_bytes)
    return image_b64


async def load_image_as_base64_from_bytes_async(image_bytes: bytes) -> bytes:
    """
    Asynchronously encodes a bytes object containing image data to base64 format.

    This function takes raw image bytes and converts them to base64 encoding in a
    non-blocking way by using a separate thread. This is useful for handling large
    images without blocking the event loop.

    Args:
        image_bytes (bytes): The raw image data to be encoded.

    Returns:
        bytes: The base64 encoded image data.
    """
    # Use asyncio.to_thread to run the CPU-bound task in a separate thread
    image_b64 = await asyncio.to_thread(base64.b64encode, image_bytes)
    return image_b64
