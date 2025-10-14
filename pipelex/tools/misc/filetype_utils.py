import base64
import binascii
from pathlib import Path

import filetype
from pydantic import BaseModel

from pipelex import log
from pipelex.system.exceptions import ToolException


class FileTypeException(ToolException):
    pass


class FileType(BaseModel):
    extension: str
    mime: str


def detect_file_type_from_path(path: str | Path) -> FileType:
    """Detect the file type of a file at a given path.

    Args:
        path: The path to the file to detect the type of.

    Returns:
        A FileType object containing the file extension and MIME type of the file.

    Raises:
        FileTypeException: If the file type cannot be identified.

    """
    kind = filetype.guess(path)  # pyright: ignore[reportUnknownMemberType]
    if kind is None:
        msg = f"Could not identify file type of '{path!s}'"
        raise FileTypeException(msg)
    extension = f"{kind.extension}"
    mime = f"{kind.mime}"
    return FileType(extension=extension, mime=mime)


def detect_file_type_from_bytes(buf: bytes) -> FileType:
    """Detect the file type of a given bytes object.

    Args:
        buf: The bytes object to detect the type of.

    Returns:
        A FileType object containing the file extension and MIME type of the file.

    Raises:
        FileTypeException: If the file type cannot be identified.

    """
    kind = filetype.guess(buf)  # pyright: ignore[reportUnknownMemberType]
    if kind is None:
        msg = f"Could not identify file type of given bytes: {buf[:300]!r}"
        raise FileTypeException(msg)
    extension = f"{kind.extension}"
    mime = f"{kind.mime}"
    return FileType(extension=extension, mime=mime)


def detect_file_type_from_base64(b64: str | bytes) -> FileType:
    """Detect the file type of a given Base-64-encoded string.

    Args:
        b64: The Base-64-encoded bytes or string to detect the type of.

    Returns:
        A FileType object containing the file extension and MIME type of the file.

    Raises:
        FileTypeException: If the file type cannot be identified.

    """
    # Normalise to bytes holding only the Base-64 alphabet
    if isinstance(b64, bytes):
        log.debug(f"b64 is already bytes: {b64[:100]!r}")
        b64_bytes = b64
    else:  # str  →  handle optional data-URL header
        log.debug(f"b64 is a string: {b64[:100]!r}")
        if b64.lstrip().startswith("data:") and "," in b64:
            b64 = b64.split(",", 1)[1]
        log.debug(f"b64 after split: {b64[:100]!r}")
        b64_bytes = b64.encode("ascii")  # Base-64 is pure ASCII

    try:
        raw = base64.b64decode(b64_bytes, validate=True)
    except binascii.Error as exc:  # malformed Base-64
        msg = f"Could not identify file type of given bytes because input is not valid Base-64: {exc}\n{b64_bytes[:100]!r}"
        raise FileTypeException(msg) from exc

    return detect_file_type_from_bytes(buf=raw)
