import base64
import binascii
import mimetypes
from pathlib import Path
from typing import Final

import filetype
from pydantic import BaseModel

from pipelex import log
from pipelex.system.exceptions import ToolError

# Constant for unknown/undetectable file types
UNKNOWN_FILE_TYPE = "unknown"

# Deterministic overrides for common/ambiguous MIME types
_MIME_OVERRIDES: Final[dict[str, str]] = {
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "text/plain": "txt",
    "application/json": "json",
}

# Initialize MIME database with additional types
_MIME_DB: Final[mimetypes.MimeTypes] = mimetypes.MimeTypes()
_MIME_DB.add_type("application/json", ".json", strict=True)
# Office Open XML formats (not always in default mimetypes DB)
_MIME_DB.add_type("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx", strict=True)
_MIME_DB.add_type("application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx", strict=True)
_MIME_DB.add_type("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx", strict=True)


class FileTypeError(ToolError):
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
        FileTypeError: If the file type cannot be identified.

    """
    kind = filetype.guess(path)  # pyright: ignore[reportUnknownMemberType]
    if kind is None:
        msg = f"Could not identify file type of '{path!s}'"
        raise FileTypeError(msg)
    extension = f"{kind.extension}"
    mime = f"{kind.mime}"
    return FileType(extension=extension, mime=mime)


def detect_file_type_from_bytes(raw_bytes: bytes) -> FileType:
    """Detect the file type of a given bytes object.

    Args:
        raw_bytes: The bytes object to detect the type of.

    Returns:
        A FileType object containing the file extension and MIME type of the file.

    Raises:
        FileTypeError: If the file type cannot be identified.

    """
    kind = filetype.guess(raw_bytes)  # pyright: ignore[reportUnknownMemberType]
    if kind is None:
        msg = f"Could not identify file type of given bytes: {raw_bytes[:300]!r}"
        raise FileTypeError(msg)
    extension = f"{kind.extension}"
    mime = f"{kind.mime}"
    return FileType(extension=extension, mime=mime)


def detect_file_type_from_base64(base64_data: str | bytes) -> FileType:
    """Detect the file type of a given Base-64-encoded string.

    Args:
        base64_data: The base64-encoded bytes or string to detect the type of.

    Returns:
        A FileType object containing the file extension and MIME type of the file.

    Raises:
        FileTypeError: If the file type cannot be identified.

    """
    # Normalise to bytes holding only the Base-64 alphabet
    if isinstance(base64_data, bytes):
        log.verbose(f"b64 is already bytes: {base64_data[:100]!r}")
        base64_bytes = base64_data
    else:  # str  →  handle optional data-URL header
        log.verbose(f"b64 is a string: {base64_data[:100]!r}")
        if base64_data.lstrip().startswith("data:") and "," in base64_data:
            base64_data = base64_data.split(",", 1)[1]
        log.verbose(f"b64 after split: {base64_data[:100]!r}")
        base64_bytes = base64_data.encode("ascii")  # Base-64 is pure ASCII

    try:
        raw = base64.b64decode(base64_bytes, validate=True)
    except binascii.Error as exc:  # malformed Base-64
        msg = f"Could not identify file type of given bytes because input is not valid base64: {exc}\n{base64_bytes[:100]!r}"
        raise FileTypeError(msg) from exc

    return detect_file_type_from_bytes(raw_bytes=raw)


def mime_type_to_extension(mime_type: str) -> str:
    """Convert MIME type to file extension using the mimetypes database.

    Args:
        mime_type: The MIME type string (e.g., "application/pdf", "image/png").
            May include parameters (e.g., "text/plain; charset=utf-8").

    Returns:
        The file extension without leading dot (e.g., "pdf", "png").
        Returns UNKNOWN_FILE_TYPE if the MIME type is not recognized.

    Examples:
        >>> mime_type_to_extension("application/pdf")
        "pdf"
        >>> mime_type_to_extension("image/png")
        "png"
        >>> mime_type_to_extension("image/jpeg")
        "jpeg"
        >>> mime_type_to_extension("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        "docx"
    """
    # Strip parameters (e.g., "text/plain; charset=utf-8" -> "text/plain")
    base = mime_type.split(";", 1)[0].strip().lower()
    if not base:
        return UNKNOWN_FILE_TYPE

    # Check explicit overrides first
    if base in _MIME_OVERRIDES:
        return _MIME_OVERRIDES[base]

    # Use mimetypes database (try strict first, then non-strict)
    ext = _MIME_DB.guess_extension(base, strict=True) or _MIME_DB.guess_extension(base, strict=False)
    if not ext:
        return UNKNOWN_FILE_TYPE

    # Normalize jpeg variants
    ext = ext.lower()
    if base == "image/jpeg" and ext in {".jpe", ".jpeg"}:
        return "jpeg"

    # Remove leading dot
    return ext.removeprefix(".")
