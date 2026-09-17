"""What a record carries beyond its message: the bound context, the call's fields and the structured content.

All three become attributes of the stdlib ``LogRecord``, which is where a sink reads them. The stdlib
refuses an ``extra`` key that would overwrite one of the record's own attributes, and a library's log
call never raises, so a colliding entry is carried under a prefixed name instead. The collision is read
off the record actually built, through whatever record factory is installed, so an attribute a factory
added is a collision too rather than the stdlib's ``KeyError``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pipelex.tools.log.log_holding import FORWARDED_MARK

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pipelex.tools.log.log_context import LogContext

# The attribute a ``dict`` or ``list`` content is carried under, JSON-ready, beside its console rendering.
DATA_FIELD = "data"

# The prefix an entry takes when its name is one the record already owns.
COLLIDING_FIELD_PREFIX = "field_"

# The attribute the redaction stamps on a record it could not strip, and takes back off the moment it
# has. It is the fail-closed half of the scrub: a record still carrying it reaches no sink, because what
# it carries is whatever the call put there and the scrub never read. It is set before the stripping
# rather than after the failure, so a stripping that dies partway leaves it behind rather than needing a
# second thing to go right at the moment the first one went wrong.
UNSCRUBBED_MARK = "_pipelex_unscrubbed"

# Names a fresh record does not carry, so a ``hasattr`` check alone would let a caller's entry land on
# one of them. ``message`` and ``asctime`` are set by the formatter rather than by the constructor, and
# the stdlib refuses them all the same. ``FORWARDED_MARK`` is stamped by the holding handler on a
# record it has already forwarded, and an entry landing on it unprefixed would have the record rejected
# from every sink by ``ForwardedRecordFilter``: a caller's own field silently deleting its own line.
# ``UNSCRUBBED_MARK`` is the same shape of hazard on the redaction's side: an entry landing on it would
# have a perfectly ordinary record read as one the scrub could not strip, and dropped.
FORMATTER_OWNED_ATTRIBUTES = frozenset({"message", "asctime", FORWARDED_MARK, UNSCRUBBED_MARK})

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

    A field overrides the context for its record, so a call site that names a request it is not
    running under can say so; structured content owns ``data`` outright.

    ``data`` is the dispatch's own name, so a caller's entry spelled that way is carried under the
    collision prefix whether or not this call has structured content to put there. Owning it only when
    the content happens to be structured would leave a caller's ``data`` on the record's own ``data``
    beside a string content — where the runtime treats it as its own rendering and hands it to a sink
    with its control characters intact, which is exactly the forged line the escaping exists to stop.
    """
    extra: dict[str, Any] = {}
    if context is not None:
        extra.update(context.fields)
    if fields:
        extra.update(fields)
    if DATA_FIELD in extra:
        name = f"{COLLIDING_FIELD_PREFIX}{DATA_FIELD}"
        while name in extra:
            name = f"{COLLIDING_FIELD_PREFIX}{name}"
        extra[name] = extra.pop(DATA_FIELD)
    if data is not None:
        extra[DATA_FIELD] = data
    return extra


def attach_log_record_extra(*, record: logging.LogRecord, extra: Mapping[str, Any]) -> None:
    """Set each entry as an attribute of the record, under a prefixed name when the record already owns that name.

    The record was built by the logger, through the installed record factory, so what it owns is exactly
    what the stdlib's own ``makeRecord`` would refuse: its declared attributes, anything a factory stamped
    on it, and what the ``LogRecord`` class itself owns, ``getMessage`` and the dunders among them, which
    a lookup in the instance dict alone would miss. The prefix is applied until the name lands on an
    attribute nobody owns, and entries are attached in order, so an entry attached earlier under a
    prefixed name is owned for the entries after it: whatever the order of the mapping, no value is lost.
    """
    for name, value in extra.items():
        attribute = name
        while hasattr(record, attribute) or attribute in FORMATTER_OWNED_ATTRIBUTES:
            attribute = f"{COLLIDING_FIELD_PREFIX}{attribute}"
        setattr(record, attribute, value)


def carried_attributes(*, record: logging.LogRecord) -> dict[str, Any]:
    """Everything on the record that is not the stdlib's: the fields, the context identifiers, ``data``, a factory's stamps.

    Read the way a structured sink reads a record, in the order the attributes were attached. A value is
    handed back as the call gave it: a sink serializes it when it emits, on the calling thread.
    """
    return {name: value for name, value in vars(record).items() if name not in STDLIB_RECORD_ATTRIBUTES}
