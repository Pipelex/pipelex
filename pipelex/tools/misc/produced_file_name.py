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


def _fitted_name(*, base: str, suffix: str, extension: str) -> str | None:
    """`base`, `suffix` and `extension` joined and capped at `MAX_FILE_NAME_BYTES`, the base shortened to fit, or None.

    An extension so long that, with the suffix, it leaves no byte for the base is dropped: the cap holds whatever the
    runtime's name carried. None when nothing is left of the base.
    """
    suffix_bytes = len(suffix.encode("utf-8"))
    room = MAX_FILE_NAME_BYTES - suffix_bytes - len(extension.encode("utf-8"))
    if room < 1:
        extension = ""
        room = MAX_FILE_NAME_BYTES - suffix_bytes
    shortened = _truncate_to_bytes(text=base, max_bytes=room)
    if len(shortened) < len(base):
        shortened = shortened.rstrip(" .")
    if not shortened:
        return None
    return f"{shortened}{suffix}{extension}"


def capped_runtime_name(*, default_name: str) -> str:
    """The name the runtime would have given the file, capped at `MAX_FILE_NAME_BYTES` like a rendered name.

    Its stem is shortened, at a character boundary, keeping its extension when the extension leaves room for it.
    """
    if len(default_name.encode("utf-8")) <= MAX_FILE_NAME_BYTES:
        return default_name
    extension = default_extension(default_name=default_name)
    stem = default_name[: len(default_name) - len(extension)] if extension else default_name
    return _fitted_name(base=stem, suffix="", extension=extension) or _truncate_to_bytes(text=default_name, max_bytes=MAX_FILE_NAME_BYTES)


def build_produced_file_name(*, rendered: str | None, default_name: str, item_number: int = 1) -> str:
    """The name of a produced file, from the rendered `output_filename` and the name the runtime would have given it.

    Args:
        rendered: The rendered template, or `None` when rendering failed.
        default_name: The name the runtime would have given the file, whose extension the name keeps.
        item_number: The file's position among the items of a plural output, from 1: the second and later items take
            ` (2)`, ` (3)` and so on before the extension, since the template is rendered once for all of them.

    Returns:
        The name, never longer than `MAX_FILE_NAME_BYTES` in UTF-8, or `default_name`, capped the same way, when rendering
        failed or nothing is left before the extension.
    """
    fallback = capped_runtime_name(default_name=default_name)
    if rendered is None:
        return fallback
    cleaned = clean_rendered_name(rendered=rendered)
    extension = default_extension(default_name=default_name)
    base = cleaned
    if extension and cleaned.lower().endswith(extension.lower()):
        # The name already ends with the extension, as the author wrote it: it is kept, letter case included.
        base = cleaned[: -len(extension)]
        extension = cleaned[-len(extension) :]
    if not base.strip(" ."):
        return fallback
    suffix = f" ({item_number})" if item_number > 1 else ""
    return _fitted_name(base=base, suffix=suffix, extension=extension) or fallback
