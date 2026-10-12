"""The file name an object is stored under, held to the grammar every `pipelex-storage://` reader accepts.

A host that serves a run's files by their `pipelex-storage://` URI checks each key before it reads it, and the hosted
Pipelex platform's check is the strictest this runtime writes for: every segment of the key is `[A-Za-z0-9_-]+`, and the
last one is a stem of those characters, one dot and an alphanumeric extension. A name holding any other character, a
letter outside ASCII or a second dot, stores without complaint and is then refused by every reader holding that
grammar, so the file can never be downloaded. A name a method renders, such as a `PipeDocGen` step's `filename`, or a
name a caller sends, such as a template file's, is therefore made into one the grammar accepts before anything is
stored under it.
"""

import re
import unicodedata
from typing import Final

# The grammar of a stored file's name: a stem, one dot, an extension. Restated from the hosted platform's storage URI
# parser, which the runtime does not import.
STORAGE_FILE_STEM_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_-]+$")
STORAGE_FILE_EXTENSION_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9]+$")

# Long enough for any name a person reads, short enough that a key stays far below a store's own limit.
MAX_STORAGE_FILE_STEM_LENGTH: Final[int] = 120

# The stem when neither the name nor its fallback leaves anything, and the extension when the given one leaves nothing.
_LAST_RESORT_STEM: Final[str] = "file"
_LAST_RESORT_EXTENSION: Final[str] = "bin"

# Letters that NFKD leaves whole, since Unicode treats each as a letter of its own rather than a base letter carrying a
# mark, spelled with the Latin letters a reader would type for them.
_LETTERS_NFKD_KEEPS_WHOLE: Final[dict[str, str]] = {
    "ø": "o",
    "Ø": "O",
    "æ": "ae",
    "Æ": "AE",
    "œ": "oe",
    "Œ": "OE",
    "ł": "l",
    "Ł": "L",
    "đ": "d",
    "Đ": "D",
    "ð": "d",
    "Ð": "D",
    "þ": "th",
    "Þ": "Th",
    "ß": "ss",
    "ẞ": "SS",
    "ı": "i",
    "ħ": "h",
    "Ħ": "H",
    "ŧ": "t",
    "Ŧ": "T",
    "ŋ": "ng",
    "Ŋ": "NG",
    "ĸ": "k",
}
_TRANSLITERATION_TABLE: Final[dict[int, str]] = str.maketrans(_LETTERS_NFKD_KEEPS_WHOLE)

# Dots are kept until a name already ending in its extension has had it removed, then go with everything else.
_NOT_STEM_OR_DOT_CHARACTERS: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9_.-]+")
_NOT_STEM_CHARACTERS: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9_-]+")
_NOT_EXTENSION_CHARACTERS: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9]+")
# A run of separators holding a hyphen becomes one hyphen; a run of underscores alone becomes one underscore.
_HYPHENATED_SEPARATOR_RUNS: Final[re.Pattern[str]] = re.compile(r"[-_]*-[-_]*")
_UNDERSCORE_RUNS: Final[re.Pattern[str]] = re.compile(r"_{2,}")
_EDGE_CHARACTERS: Final[str] = ".-_"


def fold_to_ascii(*, text: str) -> str:
    """`text` with each letter spelled in ASCII where it has a spelling there, and every other character kept as it is.

    NFKD splits a letter from its marks and a compatibility character into its plain form (`ë` into `e` and a
    diaeresis, `ﬁ` into `fi`), the marks are dropped, and the letters NFKD leaves whole are spelled from a table (`ø`
    as `o`, `ß` as `ss`). A script with no Latin spelling here, such as Greek, Cyrillic or Han, is kept for the caller
    to replace.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return without_marks.translate(_TRANSLITERATION_TABLE)


def _path_safe_stem(*, name: str, extension: str) -> str:
    """The stem `name` gives once folded to ASCII and held to the grammar, or the empty string when nothing is left."""
    stem = _NOT_STEM_OR_DOT_CHARACTERS.sub("-", fold_to_ascii(text=name)).strip(_EDGE_CHARACTERS)
    if stem.lower().endswith(f".{extension}"):
        stem = stem[: -(len(extension) + 1)]
    stem = _NOT_STEM_CHARACTERS.sub("-", stem)
    stem = _HYPHENATED_SEPARATOR_RUNS.sub("-", stem)
    stem = _UNDERSCORE_RUNS.sub("_", stem)
    return stem[:MAX_STORAGE_FILE_STEM_LENGTH].strip(_EDGE_CHARACTERS)


def path_safe_file_name(*, name: str, fallback: str, extension: str) -> str:
    """One file name every `pipelex-storage://` reader accepts, ending in `.{extension}`, from whatever `name` holds.

    Each letter is spelled in ASCII where it can be (`fold_to_ascii`), and every other character, a dot inside the
    stem included, becomes a hyphen, a run of separators collapsing into one. A name already ending in the extension
    is not given it twice, the stem is cut at `MAX_STORAGE_FILE_STEM_LENGTH` characters, and a separator left at either
    end is dropped. When nothing is left, a name written wholly in Greek or Han for one, the stem is `fallback` held to
    the same rule, then `file`.

    Args:
        name: The name to store the file under, as rendered or as sent: any text.
        fallback: The stem to use when `name` leaves none, such as the pipe's code.
        extension: The file's extension, without its dot, lowercased and kept to its ASCII letters and digits, `bin`
            when it has none.

    Returns:
        A name whose stem matches `STORAGE_FILE_STEM_PATTERN` and whose extension matches `STORAGE_FILE_EXTENSION_PATTERN`.
    """
    safe_extension = _NOT_EXTENSION_CHARACTERS.sub("", fold_to_ascii(text=extension)).lower() or _LAST_RESORT_EXTENSION
    stem = _path_safe_stem(name=name, extension=safe_extension) or _path_safe_stem(name=fallback, extension=safe_extension) or _LAST_RESORT_STEM
    return f"{stem}.{safe_extension}"
