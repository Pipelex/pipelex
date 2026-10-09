"""What the ``console`` sink shows of a record's fields: the suffix after the message and the style map.

The console renders the fields a call attached as a ``key=value`` suffix after the message, the way
structlog's console renderer and pino-pretty do, so a value moved out of a message into ``fields=`` still
reaches the person at the terminal. It renders the fields ``attach_log_record_extra`` recorded and no other
attribute, so neither the stdlib's own attributes nor Pipelex's marks nor what a record factory or a
third-party library stamped ever shows. The run identifiers and ``data`` are left out as well: the
identifiers are the same on every line of a run and would drown the message, and ``data`` is the structured
content the message already renders, which is why the dispatch never stamps a layout on a call carrying it.

A value renders on one line: a string bare unless it is empty or holds a space, an equals sign, a quote, a
backslash or a character a terminal would act on, in which case it is quoted, with a backslash and a quote
escaped by a backslash and that character written as its escape; anything else as compact JSON; and the
whole cut short past ``FIELD_VALUE_MAX_LENGTH``. A key is written the same way, so a field name holding a
line break, a space, an equals sign or an escape sequence can forge neither a line nor a pair. Redaction has
already run when the console renders a record, so what is rendered is what the scrub left.

Colour follows the name the field was given, from ``FIELD_STYLES``, wherever the field appears, and whatever
collision prefix it landed under; a field outside the map renders dimmed. The map is one table in code, the
colours the pipe announcement has always used. Nothing here imports Rich: the suffix is a list of
``(text, style)`` segments the sink turns into a Rich ``Text``, never a markup string, so a value carrying
``[red]`` prints as written whatever the handler's markup setting.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from pipelex.tools.log.log_context import PIPE_RUN_ID_FIELD, PIPELINE_RUN_ID_FIELD, REQUEST_ID_FIELD
from pipelex.tools.log.log_fields import DATA_FIELD, attached_field_names, given_field_name
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

FIELD_SEPARATOR = " "
KEY_VALUE_SEPARATOR = "="
QUOTE = '"'
ESCAPE = "\\"

# What makes a printable string quoted rather than bare: the empty string aside, a character that would
# otherwise read as the end of a pair, the start of the next or an escape, so the suffix cannot be forged.
QUOTED_CHARACTERS = frozenset({FIELD_SEPARATOR, KEY_VALUE_SEPARATOR, QUOTE, ESCAPE})

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

    The run identifiers, ``data`` and the fields a layout already presented are left out.
    """
    segments: list[StyledSegment] = []
    for name, value in fields.items():
        if name in CONSOLE_HIDDEN_FIELDS or name in presented_fields:
            continue
        segments.append((FIELD_SEPARATOR, ""))
        # The key is written like a value: a name a caller chose can hold a line break that would forge a
        # line, a space that would read as two pairs or an escape sequence the terminal would act on.
        segments.append((f"{format_field_value(value=name)}{KEY_VALUE_SEPARATOR}", FIELD_KEY_STYLE))
        segments.append((format_field_value(value=value), field_style(name=name)))
    return segments


def format_field_value(*, value: Any) -> str:
    """A field's value as the suffix prints it: one line, a string quoted when it could forge a pair, cut short when long."""
    return _truncated(text=_one_line(value=value, is_quoting_strings=True))


def format_layout_value(*, value: Any) -> str:
    """A field's value as a layout substitutes it: one line, a string as itself, cut short when long."""
    return _truncated(text=_one_line(value=value, is_quoting_strings=False))


def one_line_text(*, text: str) -> str:
    """The text with every character a terminal would act on written as its escape, so it stays on one line."""
    return "".join(character if character.isprintable() else _escaped_character(character=character) for character in text)


def _one_line(*, value: Any, is_quoting_strings: bool) -> str:
    if isinstance(value, str):
        return _string_text(text=value, is_quoting_strings=is_quoting_strings)
    if isinstance(value, float) and not math.isfinite(value):
        # ``NaN``, ``Infinity`` or ``-Infinity``, bare, as the wire sinks spell it.
        return str(spell_non_finite(value=value))
    if _renders_as_json(value=value):
        return one_line_text(text=_compact_json(value=value))
    return _string_text(text=str(value), is_quoting_strings=is_quoting_strings)


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


def _truncated(*, text: str) -> str:
    if len(text) <= FIELD_VALUE_MAX_LENGTH:
        return text
    return f"{text[: FIELD_VALUE_MAX_LENGTH - len(TRUNCATION_MARK)]}{TRUNCATION_MARK}"
