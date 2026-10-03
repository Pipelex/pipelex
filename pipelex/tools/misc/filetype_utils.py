import base64
import binascii
import mimetypes
from collections.abc import Collection
from pathlib import Path
from typing import Final

import filetype
from pydantic import BaseModel

from pipelex import log
from pipelex.tools.misc.exceptions import FileTypeError

# Constant for unknown/undetectable file types
UNKNOWN_FILE_TYPE = "unknown"

# Deterministic overrides for common/ambiguous MIME types
_MIME_OVERRIDES: Final[dict[str, str]] = {
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "text/plain": "txt",
    # Python 3.11's default table has no entry for Markdown; 3.12 added `.md`
    "text/markdown": "md",
    "application/json": "json",
}

# Initialize MIME database with additional types
_MIME_DB: Final[mimetypes.MimeTypes] = mimetypes.MimeTypes()
_MIME_DB.add_type("application/json", ".json", strict=True)
# Office Open XML formats (not always in default mimetypes DB)
_MIME_DB.add_type("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx", strict=True)
_MIME_DB.add_type("application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx", strict=True)
_MIME_DB.add_type("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx", strict=True)


class FileType(BaseModel):
    extension: str
    mime: str


def detect_file_type_from_path(path: Path) -> FileType:
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


#####################################################################################################
# Identifying a file input's format, and the format keys the format checks compare
#####################################################################################################

# How many leading bytes identify a file: exactly what `filetype` reads, so a head read of this
# size identifies a stored file as well as loading all of it would.
FILE_HEAD_NB_BYTES: Final[int] = 8192

# A declaration that says nothing: a file with this type, or with none, has no known format.
_GENERIC_MIME_TYPES: Final[frozenset[str]] = frozenset({"application/octet-stream"})

# A zip container the sniffer recognised without recognising what it contains, and the types that
# name a more precise zip-based format. An Office Open XML or OpenDocument file is a zip, and
# `filetype` names it only when its identifying entry sits among the first few, so a bare zip says
# only that the file is some zip: a declared zip-based type, or the file's name, says which.
_ZIP_MIME_TYPE: Final[str] = "application/zip"
_ZIP_BASED_DOCUMENT_MIME_PREFIXES: Final[tuple[str, ...]] = (
    "application/vnd.openxmlformats-officedocument.",
    "application/vnd.oasis.opendocument.",
)

# The family every image type belongs to, which is how models declare that they read images.
IMAGE_FORMAT_KEY: Final[str] = "image"

_FORMAT_KEY_DESCRIPTIONS: Final[dict[str, str]] = {
    "pdf": "a PDF document",
    "docx": "a Word document",
    "doc": "a Word 97-2003 document",
    "pptx": "a PowerPoint presentation",
    "ppt": "a PowerPoint 97-2003 presentation",
    "xlsx": "an Excel workbook",
    "xls": "an Excel 97-2003 workbook",
    "html": "an HTML page",
    IMAGE_FORMAT_KEY: "an image",
}


# How a list of readable formats names each key, in the order it lists them: `PDF and images`.
_FORMAT_KEY_LIST_NAMES: Final[dict[str, str]] = {
    "pdf": "PDF",
    "docx": "Word (.docx)",
    "doc": "Word 97-2003 (.doc)",
    "pptx": "PowerPoint (.pptx)",
    "ppt": "PowerPoint 97-2003 (.ppt)",
    "xlsx": "Excel (.xlsx)",
    "xls": "Excel 97-2003 (.xls)",
    "html": "HTML",
    IMAGE_FORMAT_KEY: "images",
    "web_page": "web pages",
}


def _base_mime_type(*, mime_type: str) -> str:
    """The MIME type without its parameters, lowercased: `Text/Plain; charset=utf-8` → `text/plain`."""
    return mime_type.split(";", 1)[0].strip().lower()


def format_key_from_mime_type(*, mime_type: str | None) -> str | None:
    """The format key a file of this MIME type has, which is what every format check compares.

    Every `image/*` type is the `image` family, the key models declare to say they read images. Any
    other identified type is its extension (`pdf`, `docx`, `pptx`, `xlsx`, `doc`, `html`, `md`…). No
    type, the generic `application/octet-stream`, and a type the MIME database does not know have no
    key: the format is unknown, and a check leaves an unknown format to the provider.
    """
    if mime_type is None:
        return None
    base = _base_mime_type(mime_type=mime_type)
    if not base or base in _GENERIC_MIME_TYPES:
        return None
    if base.startswith("image/"):
        return IMAGE_FORMAT_KEY
    extension = mime_type_to_extension(base)
    if extension == UNKNOWN_FILE_TYPE:
        return None
    return extension


def describe_format_key(*, format_key: str) -> str:
    """A format key in plain words, for a message: `docx` → `a Word document`, `md` → `a .md file`.

    The words carry no type: a message adds the extension or the MIME type that tells two keys apart.
    """
    if description := _FORMAT_KEY_DESCRIPTIONS.get(format_key):
        return description
    return f"a .{format_key} file"


def describe_file_format(*, format_key: str, mime_type: str | None) -> str:
    """A file's format in plain words with the type that tells it apart: `a Word document (.docx)`.

    An image is told apart by its MIME type, since every image shares the `image` key:
    `an image (image/png)`.
    """
    description = _FORMAT_KEY_DESCRIPTIONS.get(format_key)
    if description is None:
        # `a .md file` already names its extension.
        return describe_format_key(format_key=format_key)
    if format_key == IMAGE_FORMAT_KEY:
        return f"{description} ({mime_type})" if mime_type else description
    return f"{description} (.{format_key})"


def describe_format_keys(*, format_keys: Collection[str]) -> str:
    """A set of readable formats in plain words, in a stable order: `PDF, Word (.docx) and images`."""
    known_keys = [format_key for format_key in _FORMAT_KEY_LIST_NAMES if format_key in format_keys]
    other_keys = sorted(set(format_keys) - set(_FORMAT_KEY_LIST_NAMES))
    names = [_FORMAT_KEY_LIST_NAMES[format_key] for format_key in known_keys] + [f".{format_key}" for format_key in other_keys]
    if not names:
        return "no file format"
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"


def guess_file_type_from_bytes(*, raw_bytes: bytes) -> FileType | None:
    """The type the leading bytes identify, or `None` when they identify none.

    Unlike `detect_file_type_from_bytes`, which raises, this is the form for a caller that has a
    fallback: text formats (plain text, Markdown, CSV, JSON, HTML) carry no signature to sniff.
    """
    if not raw_bytes:
        return None
    kind = filetype.guess(raw_bytes[:FILE_HEAD_NB_BYTES])  # pyright: ignore[reportUnknownMemberType]
    if kind is None:
        return None
    return FileType(extension=f"{kind.extension}", mime=f"{kind.mime}")


def identify_mime_type(*, head: bytes | None, declared_mime_type: str | None, file_name: str | None) -> str | None:
    """The MIME type that describes a file, from its leading bytes, what the caller declared and its name.

    The bytes are the truth: when they identify a type, it replaces any declared one, so a
    `data:image/png` URL holding a PDF is a PDF. When they identify none, which is the case for text
    formats, the declared type stands. No head (a file that was not read) keeps the declared type.

    A sniffed bare zip is the one identification that does not settle the format: it may be an
    Office file whose identifying entry came late. An Office or OpenDocument type says which, whether
    it is declared or given by the file's name, and it wins over a bare zip from either source, so a
    `report.docx` declared `application/zip` is a Word file. A bare zip, declared or named, is a zip.
    Otherwise the format is unknown rather than a zip, so no check refuses a valid Office file for
    the order of its entries.

    Args:
        head: The file's leading bytes, `None` when it was not read.
        declared_mime_type: The type the caller declared, if any.
        file_name: The file's name or the last segment of its path, if it has one.

    Returns:
        The MIME type, `None` when the format is unknown.
    """
    sniffed = guess_file_type_from_bytes(raw_bytes=head) if head else None
    if sniffed is None:
        return declared_mime_type
    if sniffed.mime != _ZIP_MIME_TYPE:
        return sniffed.mime
    named_mime_type = _MIME_DB.guess_type(file_name, strict=True)[0] if file_name else None
    candidate_mime_types = [mime_type for mime_type in (declared_mime_type, named_mime_type) if mime_type is not None]
    for candidate_mime_type in candidate_mime_types:
        if _base_mime_type(mime_type=candidate_mime_type).startswith(_ZIP_BASED_DOCUMENT_MIME_PREFIXES):
            return candidate_mime_type
    for candidate_mime_type in candidate_mime_types:
        if _base_mime_type(mime_type=candidate_mime_type) == _ZIP_MIME_TYPE:
            return candidate_mime_type
    return None
