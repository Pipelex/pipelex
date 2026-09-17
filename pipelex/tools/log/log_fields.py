"""What a record carries beyond its message: the bound context, the call's fields and the structured content.

All three become attributes of the stdlib ``LogRecord``, which is where a sink reads them. The stdlib
refuses an ``extra`` key that would overwrite one of the record's own attributes, and a library's log
call never raises, so a colliding entry is carried under a prefixed name instead. The collision is read
off the record actually built, through whatever record factory is installed, so an attribute a factory
added is a collision too rather than the stdlib's ``KeyError``.

Pipelex's own machinery owns a name on the record too, and it is reserved here for the same reason the
``json`` sink reserves its own keys: a name nobody owns *yet* is a name a caller's field lands on freely,
and this one steers delivery. So the reserved set spans what the formatter sets later and what this
package stamps later, and neither is a field a sink reads back.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pipelex.tools.log.log_context import LogContext

# The attribute a ``dict`` or ``list`` content is carried under, JSON-ready, beside its console rendering.
DATA_FIELD = "data"

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

# The names this package stamps on a record itself. Never a field: a caller's entry of the same name is
# prefixed on the way on, and a record carrying one does not hand it to a sink as something it carries.
PIPELEX_OWNED_ATTRIBUTES = frozenset({FORWARDED_MARK})

# Reserved whether or not the record carries the name yet, which is exactly what the stdlib's own refusal
# cannot cover: both sets are stamped after the entries are attached.
RESERVED_ATTRIBUTES = FORMATTER_OWNED_ATTRIBUTES | PIPELEX_OWNED_ATTRIBUTES

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
    under can say so. Structured content owns the ``data`` name, and a field of that name is moved aside
    under the ``field_`` prefix rather than destroyed — the same discipline the record's own attributes
    and every wire sink's reserved keys follow, applied until the name lands where nothing sits, so a call
    passing both ``data`` and ``field_data`` beside structured content loses neither.
    """
    extra: dict[str, Any] = {}
    if context is not None:
        extra.update(context.fields)
    if fields:
        extra.update(fields)
    if data is not None:
        if DATA_FIELD in extra:
            displaced = f"{COLLIDING_FIELD_PREFIX}{DATA_FIELD}"
            while displaced in extra:
                displaced = f"{COLLIDING_FIELD_PREFIX}{displaced}"
            extra[displaced] = extra[DATA_FIELD]
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
    """
    for name, value in extra.items():
        attribute = name
        while hasattr(record, attribute) or attribute in RESERVED_ATTRIBUTES:
            attribute = f"{COLLIDING_FIELD_PREFIX}{attribute}"
        setattr(record, attribute, value)


def carried_attributes(*, record: logging.LogRecord) -> dict[str, Any]:
    """Everything on the record that is not the stdlib's or ours: the fields, the context identifiers, ``data``, a factory's stamps.

    Read the way a structured sink reads a record, in the order the attributes were attached. A value is
    handed back as the call gave it: a sink serializes it when it emits, on the calling thread. What this
    package stamps on a record itself is machinery and belongs on no wire, so it is left out here as it is
    reserved on the way in.
    """
    return {name: value for name, value in vars(record).items() if name not in STDLIB_RECORD_ATTRIBUTES and name not in PIPELEX_OWNED_ATTRIBUTES}
