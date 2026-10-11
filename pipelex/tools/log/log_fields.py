"""What a record carries beyond its message: the bound context, the call's fields and the structured content.

All three become attributes of the stdlib ``LogRecord``, which is where a sink reads them. The stdlib
refuses an ``extra`` key that would overwrite one of the record's own attributes, and a library's log
call never raises, so a colliding entry is carried under a prefixed name instead. The collision is read
off the record actually built, through whatever record factory is installed, so an attribute a factory
added is a collision too rather than the stdlib's ``KeyError``.

Pipelex's own machinery owns a name on the record too, and it is reserved here for the same reason the
``json`` sink reserves its own keys: a name nobody owns *yet* is a name a caller's field lands on freely,
and this one steers delivery. So the reserved set spans what the formatter sets later, what this
package stamps later and what Rich's console handler reads off a record ahead of its own settings, and
none of them is a field a sink reads back.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pipelex.tools.log.log_context import LogContext

# The attribute a ``dict`` or ``list`` content is carried under, JSON-ready, beside its console rendering.
DATA_FIELD = "data"

# The field a line's advice rides in: what its reader should do about the event, one imperative sentence, the name
# Pipelex's error reports give their advice. The message says what happened; the advice varies with the cause while
# the event does not, so it stays out of the message. The console prints it on a line of its own under the record.
USER_ACTION_FIELD = "user_action"

# The prefix an entry takes when its name is one the record already owns.
COLLIDING_FIELD_PREFIX = "field_"

# Set by the formatter rather than the constructor, so a fresh record does not carry them yet and the stdlib refuses them all the same.
FORMATTER_OWNED_ATTRIBUTES = frozenset({"message", "asctime"})

# The attribute the holding handler stamps on a record it has already forwarded to the sink's handler, and
# which that handler's forwarding filter reads to reject the root logger's own second delivery of it. The
# name lives here rather than beside the handler because reserving it is what makes it safe: it is stamped
# after the forward, so a fresh record does not own it, and a caller's field spelling it would be read as
# the marker and cost the whole record its delivery.
FORWARDED_MARK = "_pipelex_forwarded"

# Rich's per-record override of its handler's markup setting, which ``RichHandler.render_message`` reads as
# ``getattr(record, "markup", self.markup)``. The console sink reads no message as markup, and a caller's
# field landing on this name would turn markup back on for its line, where a tag-shaped span of the message,
# a ``list[int]`` or a bracketed path, is swallowed or raises.
RICH_MARKUP_ATTRIBUTE = "markup"

# Rich's per-record override of its handler's highlighter, which ``RichHandler.render_message`` reads as
# ``getattr(record, "highlighter", self.highlighter)`` and then calls on the line. A caller's field landing
# on it would be called in the highlighter's place: a string there raises, and the whole line is lost.
RICH_HIGHLIGHTER_ATTRIBUTE = "highlighter"

# Every attribute Rich's handler reads off a record ahead of its own setting: ``render_message`` reads these
# two, and nothing else ``emit`` or ``render`` reads is outside the stdlib's own attributes. Each steers the
# console alone and means nothing on a wire, so neither is a field a caller can land on nor one a sink is
# handed as something the record carries, whoever stamped it.
RICH_RECORD_OVERRIDES = frozenset({RICH_MARKUP_ATTRIBUTE, RICH_HIGHLIGHTER_ATTRIBUTE})

# The attribute the redaction stamps on a record it could not strip, and takes back off the moment it
# has. It is the fail-closed half of the scrub: a record still carrying it reaches no sink, because what
# it carries is whatever the call put there and the scrub never read. It is set before the stripping
# rather than after the failure, so a stripping that dies partway leaves it behind rather than needing a
# second thing to go right at the moment the first one went wrong.
UNSCRUBBED_MARK = "_pipelex_unscrubbed"

# The attribute naming, in order, the attributes ``attach_log_record_extra`` set on the record: the fields,
# the context identifiers and ``data`` under the names they landed on. It is how the console tells what the
# call attached from what a record factory or a third-party library stamped, which it does not render. A
# caller's field spelling it would hand the console a list of names the call never gave.
FIELD_NAMES_MARK = "_pipelex_field_names"

# The attribute carrying the console layout a call named with ``layout=``. The layout is console
# presentation: the console sink reads it, and reserving it is what keeps it off every wire, where the
# message already says what the line is. A caller's field spelling it would pick the line's layout.
LAYOUT_MARK = "_pipelex_layout"

# The names this package stamps on a record itself. Never a field: a caller's entry of the same name is
# prefixed on the way on, and a record carrying one does not hand it to a sink as something it carries.
# Reserving them is what makes each one safe, because each is stamped later than the entries are attached
# and so a fresh record owns none of them: a caller's field spelling ``FORWARDED_MARK`` would be read as
# the forwarding marker and cost the whole record its delivery, and one spelling ``UNSCRUBBED_MARK`` would
# have a perfectly ordinary record read as one the scrub could not strip, and dropped.
PIPELEX_OWNED_ATTRIBUTES = frozenset({FORWARDED_MARK, UNSCRUBBED_MARK, FIELD_NAMES_MARK, LAYOUT_MARK})

# Reserved whether or not the record carries the name yet, which is exactly what the stdlib's own refusal
# cannot cover: the formatter's and Pipelex's are stamped after the entries are attached, and Rich's are
# read by the console handler whoever set them.
RESERVED_ATTRIBUTES = FORMATTER_OWNED_ATTRIBUTES | PIPELEX_OWNED_ATTRIBUTES | RICH_RECORD_OVERRIDES

# The attributes the stdlib gives every record, read off one built by the stdlib's own constructor on
# this interpreter rather than listed by hand, so a version that adds one (``taskName`` arrived with
# 3.12) is covered. Everything else on a record is what a call, a context or a record factory put there.
STDLIB_RECORD_ATTRIBUTES: frozenset[str] = (
    frozenset(
        vars(logging.LogRecord(name="", level=logging.NOTSET, pathname="", lineno=0, msg="", args=(), exc_info=None)),
    )
    | FORMATTER_OWNED_ATTRIBUTES
)


def build_log_record_extra(
    *,
    context: LogContext | None,
    fields: Mapping[str, Any] | None,
    data: Any | None,
) -> dict[str, Any]:
    """The ``extra`` for one record, in precedence order: the bound context, then the call's fields, then the content.

    A field overrides the context for its record, so a call site that names a request it is not running
    under can say so. The ``data`` name is the dispatch's own, and a field spelled that way is moved aside
    under the ``field_`` prefix rather than destroyed — the same discipline the record's own attributes
    and every wire sink's reserved keys follow, applied until the name lands where nothing sits, so a call
    passing both ``data`` and ``field_data`` beside structured content loses neither.

    The move happens whether or not this call has structured content to put there. Owning the name only
    when the content happens to be structured would leave a caller's ``data`` on the record's own ``data``
    beside a string content — where the runtime treats it as its own rendering and hands it to a sink
    with its control characters intact, which is exactly the forged line the escaping exists to stop.
    """
    extra: dict[str, Any] = {}
    if context is not None:
        extra.update(context.fields)
    if fields:
        extra.update(fields)
    if DATA_FIELD in extra:
        displaced = f"{COLLIDING_FIELD_PREFIX}{DATA_FIELD}"
        while displaced in extra:
            displaced = f"{COLLIDING_FIELD_PREFIX}{displaced}"
        extra[displaced] = extra.pop(DATA_FIELD)
    if data is not None:
        extra[DATA_FIELD] = data
    return extra


def attach_log_record_extra(*, record: logging.LogRecord, extra: Mapping[str, Any]) -> None:
    """Set each entry as an attribute of the record, under a prefixed name when the record already owns that name.

    The record was built by the logger, through the installed record factory, so what it owns is exactly
    what the stdlib's own ``makeRecord`` would refuse: its declared attributes, anything a factory stamped
    on it, and what the ``LogRecord`` class itself owns, ``getMessage`` and the dunders among them, which
    a lookup in the instance dict alone would miss. Beside those, the names set later than this — the
    formatter's and this package's own — are reserved though nothing owns them yet, because a record that
    accepted one would go on to be read as having been formatted or forwarded. The prefix is applied until
    the name lands on an attribute nobody owns, and entries are attached in order, so an entry attached
    earlier under a prefixed name is owned for the entries after it: whatever the order of the mapping, no
    value is lost.

    The names the entries landed on are recorded, in order, under ``FIELD_NAMES_MARK``, which is how the
    console tells what this call attached from what anything else stamped on the record.
    """
    attached: list[str] = []
    for name, value in extra.items():
        attribute = name
        while hasattr(record, attribute) or attribute in RESERVED_ATTRIBUTES:
            attribute = f"{COLLIDING_FIELD_PREFIX}{attribute}"
        setattr(record, attribute, value)
        attached.append(attribute)
    already_attached: tuple[str, ...] = record.__dict__.get(FIELD_NAMES_MARK, ())
    record.__dict__[FIELD_NAMES_MARK] = (*already_attached, *attached)


def given_field_name(*, name: str) -> str:
    """The name a field was given, read off the name it landed on with every collision prefix taken off.

    A field lands under a prefixed name whenever the record already owns the one the caller used, so
    whatever judges a field by its meaning, a secret's name or a colour, reads it here rather than as carried.
    """
    while name.startswith(COLLIDING_FIELD_PREFIX):
        name = name[len(COLLIDING_FIELD_PREFIX) :]
    return name


def attached_field_names(*, record: logging.LogRecord) -> tuple[str, ...]:
    """The attributes ``attach_log_record_extra`` set on the record, in order, or none for a record it never saw."""
    names: tuple[str, ...] = record.__dict__.get(FIELD_NAMES_MARK, ())
    return names


def carried_attributes(*, record: logging.LogRecord) -> dict[str, Any]:
    """Everything on the record that is not the stdlib's or ours: the fields, the context identifiers, ``data``, a factory's stamps.

    Read the way a structured sink reads a record, in the order the attributes were attached. A value is
    handed back as the call gave it: a sink serializes it when it emits, on the calling thread. What this
    package stamps on a record itself is machinery and Rich's per-record overrides steer the console alone,
    so neither belongs on a wire, and both are left out here as they are reserved on the way in.
    """
    return {
        name: value
        for name, value in vars(record).items()
        if name not in STDLIB_RECORD_ATTRIBUTES and name not in PIPELEX_OWNED_ATTRIBUTES and name not in RICH_RECORD_OVERRIDES
    }
