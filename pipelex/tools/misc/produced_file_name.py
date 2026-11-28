"""Build the name of a file a pipe produces from its rendered `output_filename` (spec: mthds-format.md, "Naming Produced Files").

The rendered text is a name for the person who downloads the file, never a path: it is normalized, stripped of every
character a file system or a download would misread, given the extension of the name the runtime would have given the
file, and capped at 255 bytes in UTF-8. Naming a file never fails a run: when nothing usable is left, the file keeps the
name the runtime would have given it.
"""

import re
import unicodedata
from pathlib import PurePosixPath

MAX_FILE_NAME_BYTES = 255
"""The longest name most file systems accept, in bytes of its UTF-8 encoding, extension and suffix included."""

_FORBIDDEN_CHARACTERS = frozenset('/\\:*?"<>|')
"""The characters the standard turns into `-`, beside every control character: separators and the characters a file system reserves."""

_WHITE_SPACE_RUN = re.compile(r"\s+")

_WINDOWS_RESERVED_STEMS = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{index}" for index in range(1, 10)), *(f"LPT{index}" for index in range(1, 10))}
)
"""Device names Windows refuses as a file's stem whatever its extension, compared ignoring letter case."""


def default_extension(*, default_name: str) -> str:
    """The extension of the name the runtime would have given the file, with its dot, or the empty string when it has none."""
    return PurePosixPath(default_name).suffix


def clean_rendered_name(*, rendered: str) -> str:
    """The rendered text made safe as a name, before any extension: step 1 of the standard, and a reserved device name kept off.

    The text is normalized to NFC, every run of white space becomes one space, every separator, reserved character and
    control character becomes `-`, and white space and dots are trimmed from both ends. A stem that is a device name
    Windows reserves, such as `CON`, takes a trailing `_`, so the file opens on every system.
    """
    normalized = unicodedata.normalize("NFC", rendered)
    spaced = _WHITE_SPACE_RUN.sub(" ", normalized)
    replaced = "".join("-" if character in _FORBIDDEN_CHARACTERS or unicodedata.category(character) == "Cc" else character for character in spaced)
    # White space is all single spaces by now, so trimming spaces and dots trims "white space and dots".
    cleaned = replaced.strip(" .")
    stem = cleaned.split(".", 1)[0]
    if stem.upper() in _WINDOWS_RESERVED_STEMS:
        cleaned = f"{stem}_{cleaned[len(stem) :]}"
    return cleaned


def _truncate_to_bytes(*, text: str, max_bytes: int) -> str:
    """The longest prefix of `text` whose UTF-8 encoding fits in `max_bytes`, never splitting a character."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def build_produced_file_name(*, rendered: str | None, default_name: str, item_number: int = 1) -> str:
    """The name of a produced file, from the rendered `output_filename` and the name the runtime would have given it.

    Args:
        rendered: The rendered template, or `None` when rendering failed.
        default_name: The name the runtime would have given the file, whose extension the name keeps.
        item_number: The file's position among the items of a plural output, from 1: the second and later items take
            ` (2)`, ` (3)` and so on before the extension, since the template is rendered once for all of them.

    Returns:
        The name, or `default_name` when rendering failed or nothing is left before the extension.
    """
    if rendered is None:
        return default_name
    cleaned = clean_rendered_name(rendered=rendered)
    extension = default_extension(default_name=default_name)
    base = cleaned
    if extension and cleaned.lower().endswith(extension.lower()):
        # The name already ends with the extension, as the author wrote it: it is kept, letter case included.
        base = cleaned[: -len(extension)]
        extension = cleaned[-len(extension) :]
    if not base.strip(" ."):
        return default_name
    suffix = f" ({item_number})" if item_number > 1 else ""
    room = MAX_FILE_NAME_BYTES - len(suffix.encode("utf-8")) - len(extension.encode("utf-8"))
    shortened = _truncate_to_bytes(text=base, max_bytes=room)
    if len(shortened) < len(base):
        shortened = shortened.rstrip(" .")
    if not shortened:
        return default_name
    return f"{shortened}{suffix}{extension}"
