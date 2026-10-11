"""What the ``console`` sink shows of a record's fields: the suffix after the message and the style map.

The console renders the fields a call attached as a ``key=value`` suffix after the message, the way
structlog's console renderer and pino-pretty do, so a value moved out of a message into ``fields=`` still
reaches the person at the terminal. It renders the fields ``attach_log_record_extra`` recorded and no other
attribute, so neither the stdlib's own attributes nor Pipelex's marks nor what a record factory or a
third-party library stamped ever shows. The run identifiers and ``data`` are left out as well: the
identifiers are the same on every line of a run and would drown the message, and ``data`` is the structured
content the message already renders, which is why the dispatch never stamps a layout on a call carrying it.

A value renders on one line: a string as itself, anything else as compact JSON, and the text either gives bare unless
it is empty or holds a space, an equals sign, a quote, a backslash or a character a terminal would act on, in which
case it is quoted, with a backslash and a quote escaped by a backslash and that character written as its escape. So a
list of strings, whose JSON holds quotes, is always quoted, while a number or a list of numbers stays bare. The text
is cut short past ``FIELD_VALUE_MAX_LENGTH``, or past the generous length ``FIELD_MAX_LENGTHS`` gives a field of its
own, a handled exception's text and a template finding's. A value is cut at its end, except a path's, or a list of
paths', which is cut at its start so the last file's name stays: a field is taken for a path by its name, one ending
in ``LEFT_CUT_FIELD_SUFFIXES`` (``file.path``, ``root_path``, ``override_paths``, ``library_dirs``, ``template_file``)
or one listed whole in ``LEFT_CUT_FIELDS``. The text is cut before it is quoted and escaped, a string's own or a
JSON rendering alike, so a quoted value keeps both its quotes and no escape is split, and the cut can never leave an
unbalanced quote or bracket whose tail reads as another pair. A key is written the same way, so a field name holding a
line break, a space, an equals sign or an escape sequence can forge neither a line nor a pair. Redaction has already
run when the console renders a record, so what is rendered is what the scrub left.

A record's advice, its ``user_action`` field, is not part of the suffix: it prints whole on a line of its own under the
record, after ``ADVICE_MARK``, since it is what the reader acts on.

Colour follows the name the field was given, from ``FIELD_STYLES``, wherever the field appears, and whatever
collision prefix it landed under; a field outside the map renders dimmed. The map is one table in code, the
colours the pipe announcement has always used. Nothing here imports Rich: the suffix is a list of
``(text, style)`` segments the sink turns into a Rich ``Text``, never a markup string, so a value carrying
``[red]`` prints as written.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from pipelex.tools.log.error_fields import ERROR_MESSAGE_FIELD
from pipelex.tools.log.log_context import PIPE_RUN_ID_FIELD, PIPELINE_RUN_ID_FIELD, REQUEST_ID_FIELD
from pipelex.tools.log.log_fields import DATA_FIELD, USER_ACTION_FIELD, attached_field_names, given_field_name
from pipelex.tools.log.log_sink import json_fallback, spell_non_finite

if TYPE_CHECKING:
    import logging

# The style of a field's value, by the field's name. A concept is bold green, a pipe code red, a pipe type
# white, a stuff name cyan and a domain bold magenta: the colours the pipe announcement and the stuff
# renderings have always used, so a value keeps its colour when it moves from a message into a field.
FIELD_STYLES: dict[str, str] = {
    "pipe_code": "red",
    "pipe_type": "white",
    "output_concept": "bold green",
    "concept_ref": "bold green",
    "concept_code": "bold green",
    "stuff_name": "cyan",
    "domain_code": "bold magenta",
}

# The style of a value whose field is not in the map, and of every key.
UNMAPPED_FIELD_STYLE = "dim"
FIELD_KEY_STYLE = "dim"

# What the console never repeats after a message: the run identifiers, bound once for a whole run, and
# ``data``, the structured content the message already renders. The dispatch stamps a layout only on a
# call whose content is a string, so a layout never hides the message that renders that content.
CONSOLE_HIDDEN_FIELDS = frozenset({REQUEST_ID_FIELD, PIPELINE_RUN_ID_FIELD, PIPE_RUN_ID_FIELD, DATA_FIELD})

# The longest a rendered value gets, the truncation mark included.
FIELD_VALUE_MAX_LENGTH = 80
TRUNCATION_MARK = "…"

# The longest a handled exception's text gets, the truncation mark included. Its diagnosis, a cause chain or a parse
# error's location, is lost to a fragment cut at the length above, yet a dependency's raw output, a validation
# error's every line or git's stderr, would flood the console uncut.
ERROR_MESSAGE_MAX_LENGTH = 2000

# The text of a PipeDocGen template finding, which is the actionable part of its warning, as a handled exception's
# text is the actionable part of its line.
FINDING_MESSAGE_FIELD = "finding_message"

# The fields the console cuts at a length of their own, by the name the caller gave them.
FIELD_MAX_LENGTHS: dict[str, int] = {ERROR_MESSAGE_FIELD: ERROR_MESSAGE_MAX_LENGTH, FINDING_MESSAGE_FIELD: ERROR_MESSAGE_MAX_LENGTH}

# The endings of a field's name that say it carries a path or a list of paths, which the console cuts at its start
# rather than at its end: what tells one file from another is its name, at the end, while the start is the directory
# most lines of a run share. ``file.path`` ends in the first, and the vocabulary names a path ``<what>_path``, a list
# of paths ``<what>_paths``, a directory ``<what>_dir`` and a file ``<what>_file``, with their plurals. A list of paths
# is cut the same way, its rendering at its start, so the last path's file name stays. A path that is not on disk,
# ``url.path`` or a ``variable_path`` into working memory, is cut at its start too, its end being what tells it apart.
LEFT_CUT_FIELD_SUFFIXES: tuple[str, ...] = (".path", "_path", "_paths", "_dir", "_dirs", "_file", "_files")

# The fields the console cuts at their start that no ending above reaches, by the name the caller gave them: a file's
# name alone, and a storage key, whose end is the name of the file stored under it.
LEFT_CUT_FIELDS = frozenset({"file.name", "storage_key"})

FIELD_SEPARATOR = " "
KEY_VALUE_SEPARATOR = "="
QUOTE = '"'
ESCAPE = "\\"

# What makes a printable string quoted rather than bare: the empty string aside, a character that would
# otherwise read as the end of a pair, the start of the next or an escape, so the suffix cannot be forged.
QUOTED_CHARACTERS = frozenset({FIELD_SEPARATOR, KEY_VALUE_SEPARATOR, QUOTE, ESCAPE})

# What starts the line the advice of a record prints on, under the record, and the style the advice is printed in.
ADVICE_MARK = "→ "
ADVICE_STYLE = "cyan"

# A segment of the suffix: its text, and the Rich style it is printed in.
StyledSegment = tuple[str, str]


def attached_fields(*, record: logging.LogRecord) -> dict[str, Any]:
    """Everything the call attached to the record, under the names it landed on and in the order it was attached.

    The fields, the context identifiers and ``data`` alike: what a layout may read. The suffix leaves some of
    them out, which ``field_suffix_segments`` decides.
    """
    fields: dict[str, Any] = {}
    for name in attached_field_names(record=record):
        if name in record.__dict__:
            fields[name] = record.__dict__[name]
    return fields


def field_style(*, name: str) -> str:
    """The style a field's value is printed in: the entry in ``FIELD_STYLES`` for the name it was given, else dimmed.

    Read off the name the caller gave rather than the one it landed on, so a ``pipe_code`` that a record
    factory pushed to ``field_pipe_code`` keeps its colour.
    """
    return FIELD_STYLES.get(given_field_name(name=name), UNMAPPED_FIELD_STYLE)


def field_suffix_segments(*, fields: Mapping[str, Any], presented_fields: frozenset[str]) -> list[StyledSegment]:
    """The suffix for these fields, a space before each ``key=value``, as styled segments; none when nothing is left to show.

    The run identifiers, ``data``, the fields a layout already presented and the advice, which prints on a line of its
    own, are left out.
    """
    segments: list[StyledSegment] = []
    for name, value in fields.items():
        if name in CONSOLE_HIDDEN_FIELDS or name in presented_fields or given_field_name(name=name) == USER_ACTION_FIELD:
            continue
        segments.append((FIELD_SEPARATOR, ""))
        # The key is written like a value: a name a caller chose can hold a line break that would forge a
        # line, a space that would read as two pairs or an escape sequence the terminal would act on.
        segments.append((f"{format_field_value(value=name)}{KEY_VALUE_SEPARATOR}", FIELD_KEY_STYLE))
        rendered_value = format_field_value(value=value, max_length=field_max_length(name=name), is_cut_at_start=field_is_cut_at_start(name=name))
        segments.append((rendered_value, field_style(name=name)))
    return segments


def advice_segments(*, fields: Mapping[str, Any]) -> list[StyledSegment]:
    """The advice the fields carry under ``USER_ACTION_FIELD``, as the line printed under the record; none when they carry none.

    The advice is written whole, on one line, since it is the part of the record its reader acts on: a string as
    itself, anything else as compact JSON, every character a terminal would act on escaped. Read off the name the
    caller gave rather than the one it landed on, as the style is.
    """
    segments: list[StyledSegment] = []
    for name, value in fields.items():
        if given_field_name(name=name) != USER_ACTION_FIELD:
            continue
        string_text = _string_value_text(value=value)
        advice = one_line_text(text=string_text if string_text is not None else _non_string_text(value=value))
        segments.append((f"\n{ADVICE_MARK}{advice}", ADVICE_STYLE))
    return segments


def field_max_length(*, name: str) -> int:
    """The longest the console writes a field's value: its entry in ``FIELD_MAX_LENGTHS``, else ``FIELD_VALUE_MAX_LENGTH``.

    Read off the name the caller gave rather than the one it landed on, as the style is.
    """
    return FIELD_MAX_LENGTHS.get(given_field_name(name=name), FIELD_VALUE_MAX_LENGTH)


def field_is_cut_at_start(*, name: str) -> bool:
    """Whether the console cuts a field's value at its start, keeping its end: a path's, or a list of paths'.

    A field is taken for a path by its name: one ending in ``LEFT_CUT_FIELD_SUFFIXES``, or one of ``LEFT_CUT_FIELDS``.
    Read off the name the caller gave rather than the one it landed on, as the style is.
    """
    given_name = given_field_name(name=name)
    return given_name in LEFT_CUT_FIELDS or given_name.endswith(LEFT_CUT_FIELD_SUFFIXES)


def format_field_value(*, value: Any, max_length: int = FIELD_VALUE_MAX_LENGTH, is_cut_at_start: bool = False) -> str:
    """A field's value as the suffix prints it: one line, quoted when it could forge a pair, cut short past ``max_length``.

    The cut drops the end of the value and marks it with a trailing ``TRUNCATION_MARK``, or, with ``is_cut_at_start``,
    drops its start and marks it with a leading one. The value's text, a string's own or a JSON rendering, is cut before
    it is quoted and escaped: cutting the quoted rendering would drop a quote, or split an escape, and the value's tail
    would then read as pairs of its own, ``file.path=…/file fake=value.txt"``. A JSON rendering is quoted by the same
    rule as a string, since a cut one can leave a string unterminated, ``paths=["/x/My dir/a b=c/…``, whose tail reads
    as a pair of its own.
    """
    string_text = _string_value_text(value=value)
    text = string_text if string_text is not None else _non_string_text(value=value)
    cut_text = _truncated_at_start(text=text, max_length=max_length) if is_cut_at_start else _truncated(text=text, max_length=max_length)
    return _string_text(text=cut_text, is_quoting_strings=True)


def format_layout_value(*, value: Any) -> str:
    """A field's value as a layout substitutes it: one line, a string as itself, cut short when long."""
    return _truncated(text=_one_line(value=value, is_quoting_strings=False), max_length=FIELD_VALUE_MAX_LENGTH)


def one_line_text(*, text: str) -> str:
    """The text with every character a terminal would act on written as its escape, so it stays on one line."""
    return "".join(character if character.isprintable() else _escaped_character(character=character) for character in text)


def _one_line(*, value: Any, is_quoting_strings: bool) -> str:
    string_text = _string_value_text(value=value)
    if string_text is not None:
        return _string_text(text=string_text, is_quoting_strings=is_quoting_strings)
    return one_line_text(text=_non_string_text(value=value))


def _non_string_text(*, value: Any) -> str:
    """The text of a value not written as a string: a non-finite float's spelling, else compact JSON, neither escaped yet."""
    if isinstance(value, float) and not math.isfinite(value):
        # ``NaN``, ``Infinity`` or ``-Infinity``, bare, as the wire sinks spell it.
        return str(spell_non_finite(value=value))
    return _compact_json(value=value)


def _string_value_text(*, value: Any) -> str | None:
    """The raw text of a value written as a string, a string itself or what is neither JSON nor a non-finite float; else ``None``."""
    if isinstance(value, str):
        return value
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if _renders_as_json(value=value):
        return None
    return str(value)


def _renders_as_json(*, value: Any) -> bool:
    """Whether a value renders as compact JSON: ``None``, a boolean, a number, a mapping, a list, a tuple or a model."""
    return value is None or isinstance(value, (bool, int, float, Mapping, list, tuple, BaseModel))


def _string_text(*, text: str, is_quoting_strings: bool) -> str:
    if not is_quoting_strings:
        return one_line_text(text=text)
    if text and text.isprintable() and QUOTED_CHARACTERS.isdisjoint(text):
        return text
    # The backslashes first, so the ones escaping a quote, and the ones the terminal escapes bring, are
    # never doubled: a backslash in the text reads ``\\`` and a quote ``\"``, and neither ends the value.
    escaped = one_line_text(text=text.replace(ESCAPE, f"{ESCAPE}{ESCAPE}").replace(QUOTE, f"{ESCAPE}{QUOTE}"))
    return f"{QUOTE}{escaped}{QUOTE}"


def _compact_json(*, value: object) -> str:
    """Compact JSON, a model in JSON mode, an unknown object as its text and a non-finite float as its spelling.

    What ``json`` refuses outright, a circular reference or a mapping with a non-string key, renders as its ``repr``.
    """
    try:
        return json.dumps(spell_non_finite(value=value), ensure_ascii=False, allow_nan=False, separators=(",", ":"), default=json_fallback)
    except (TypeError, ValueError):
        return repr(value)


def _escaped_character(*, character: str) -> str:
    return character.encode("unicode_escape").decode("ascii")


def _truncated(*, text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - len(TRUNCATION_MARK)]}{TRUNCATION_MARK}"


def _truncated_at_start(*, text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return f"{TRUNCATION_MARK}{text[len(text) - max_length + len(TRUNCATION_MARK) :]}"
