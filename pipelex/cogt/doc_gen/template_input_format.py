"""The format of a file a run supplies as a `PipeDocGen` step's template, judged before anything is filled.

A step with `template_input` fills the file of one of its inputs, which must be a file of the step's format: an Excel
workbook for an `xlsx` step, a Word document for a `docx` one. The caller's declared media type and the file's name
can be wrong, so the bytes are read first. An Office Open XML file is a zip whose `[Content_Types].xml` entry names
the content type of its main part, which tells a workbook from a document or a deck whatever order the zip's entries
are in; the sniffer the rest of Pipelex uses names an Office file only when its identifying entry comes first. Any
other file the bytes identify, such as a PDF, is that file. Only when the bytes say nothing, as a text file's do, does
the declared media type decide, then the suffix of the file's name.
"""

import io
import zipfile
import zlib
from pathlib import PurePosixPath
from typing import Final

from pipelex.tools.misc.filetype_utils import format_key_from_mime_type, guess_file_type_from_bytes

# The entry of an Office Open XML package that names the content type of each of its parts.
_CONTENT_TYPES_ENTRY: Final[str] = "[Content_Types].xml"
# A content-types entry is a few kilobytes; one past this is not read, and the file is judged a zip of no known kind.
_MAX_CONTENT_TYPES_BYTES: Final[int] = 1_000_000
# The format a zip is judged to be when its content types name no main part of a known Office format.
ZIP_FORMAT_KEY: Final[str] = "zip"

# The content type of each Office Open XML format's main part, by the format key every format check compares. The
# macro-enabled and template variants are told apart, so that none passes for the plain format its engine fills.
_OFFICE_MAIN_PART_CONTENT_TYPES: Final[dict[str, str]] = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
    "xlsm": "application/vnd.ms-excel.sheet.macroEnabled.main+xml",
    "xltx": "application/vnd.openxmlformats-officedocument.spreadsheetml.template.main+xml",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
    "docm": "application/vnd.ms-word.document.macroEnabled.main+xml",
    "dotx": "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml",
    "pptm": "application/vnd.ms-powerpoint.presentation.macroEnabled.main+xml",
    "potx": "application/vnd.openxmlformats-officedocument.presentationml.template.main+xml",
}


def office_format_of_zip(*, data: bytes) -> str | None:
    """The format of a zip's bytes by the main part its content types name: `xlsx`, `docx`, `pptx` or a variant of one.

    Returns `zip` for a zip whose content types name no known main part, or that has none, and None when the bytes are
    not a zip at all. The content types are read as text and searched for each known main part's declaration, so no XML
    parser reads what the caller sent.
    """
    buffer = io.BytesIO(data)
    if not zipfile.is_zipfile(buffer):
        return None
    try:
        with zipfile.ZipFile(buffer) as package:
            content_types_info = package.getinfo(_CONTENT_TYPES_ENTRY)
            if content_types_info.file_size > _MAX_CONTENT_TYPES_BYTES:
                return ZIP_FORMAT_KEY
            content_types = package.read(content_types_info).decode("utf-8", errors="replace")
    except (KeyError, zipfile.BadZipFile, NotImplementedError, RuntimeError, EOFError, zlib.error):
        # No content-types entry (KeyError), an entry compressed in a way the zip module cannot read (NotImplementedError),
        # encrypted (RuntimeError) or corrupt (BadZipFile, zlib.error), or a truncated archive (EOFError): the bytes are
        # a zip, and no Office file an engine can fill.
        return ZIP_FORMAT_KEY
    for format_key, content_type in _OFFICE_MAIN_PART_CONTENT_TYPES.items():
        if f'"{content_type}"' in content_types:
            return format_key
    return ZIP_FORMAT_KEY


def judge_file_format(*, data: bytes, mime_type: str | None, file_name: str | None) -> str | None:
    """The format key of a file, judged from its bytes first, then its media type, then its name's suffix.

    Args:
        data: The file's bytes.
        mime_type: The media type the file carries or its source gave, if any.
        file_name: The file's name, if it has one.

    Returns:
        The format key, such as `xlsx`, `docx`, `pdf` or `zip`, or None when nothing tells the format.
    """
    office_format = office_format_of_zip(data=data)
    if office_format is not None:
        return office_format
    sniffed = guess_file_type_from_bytes(raw_bytes=data)
    if sniffed is not None and (sniffed_format := format_key_from_mime_type(mime_type=sniffed.mime)) is not None:
        return sniffed_format
    if (declared_format := format_key_from_mime_type(mime_type=mime_type)) is not None:
        return declared_format
    if file_name:
        suffix = PurePosixPath(file_name).suffix.removeprefix(".").lower()
        if suffix:
            return suffix
    return None
