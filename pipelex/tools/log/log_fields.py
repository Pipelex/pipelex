"""What a record carries beyond its message: the bound context, the call's fields and the structured content.

All three become attributes of the stdlib ``LogRecord``, which is where a sink reads them. The stdlib
refuses an ``extra`` key that would overwrite one of the record's own attributes, and a library's log
call never raises, so a colliding entry is carried under a prefixed name instead. The collision is read
off the record actually built, through whatever record factory is installed, so an attribute a factory
added is a collision too rather than the stdlib's ``KeyError``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging
    from collections.abc import Mapping

    from pipelex.tools.log.log_context import LogContext

# The attribute a ``dict`` or ``list`` content is carried under, JSON-ready, beside its console rendering.
DATA_FIELD = "data"

# The prefix an entry takes when its name is one the record already owns.
COLLIDING_FIELD_PREFIX = "field_"

# Set by the formatter rather than the constructor, so a fresh record does not carry them yet and the stdlib refuses them all the same.
FORMATTER_OWNED_ATTRIBUTES = frozenset({"message", "asctime"})


def build_log_record_extra(
    *,
    context: LogContext | None,
    fields: Mapping[str, Any] | None,
    data: Any | None,
) -> dict[str, Any]:
    """The ``extra`` for one record, in precedence order: the bound context, then the call's fields, then the content.

    A field overrides the context for its record, so a call site that names a request it is not
    running under can say so; structured content owns ``data`` outright.
    """
    extra: dict[str, Any] = {}
    if context is not None:
        extra.update(context.fields)
    if fields:
        extra.update(fields)
    if data is not None:
        extra[DATA_FIELD] = data
    return extra


def attach_log_record_extra(*, record: logging.LogRecord, extra: Mapping[str, Any]) -> None:
    """Set each entry as an attribute of the record, under a prefixed name when the record already owns that name.

    The record was built by the logger, through the installed record factory, so what it owns is exactly
    what the stdlib's own ``makeRecord`` would refuse: its declared attributes and anything a factory
    stamped on it. The prefix is applied until the name lands on an attribute nobody owns, and entries
    are attached in order, so an entry attached earlier under a prefixed name is owned for the entries
    after it: whatever the order of the mapping, no value is lost.
    """
    owned = vars(record)
    for name, value in extra.items():
        attribute = name
        while attribute in owned or attribute in FORMATTER_OWNED_ATTRIBUTES:
            attribute = f"{COLLIDING_FIELD_PREFIX}{attribute}"
        setattr(record, attribute, value)
