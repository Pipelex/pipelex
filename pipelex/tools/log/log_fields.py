"""What a record carries beyond its message: the bound context, the call's fields and the structured content.

All three become attributes of the stdlib ``LogRecord`` through ``extra``, which is where a sink reads
them. The stdlib refuses an ``extra`` key that would overwrite one of the record's own attributes, and
a library's log call never raises, so a colliding field is carried under a prefixed name instead.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pipelex.tools.log.log_context import LogContext

# The attribute a ``dict`` or ``list`` content is carried under, JSON-ready, beside its console rendering.
DATA_FIELD = "data"

# The prefix a field takes when its name is one the stdlib record already owns.
COLLIDING_FIELD_PREFIX = "field_"


def _stdlib_log_record_attributes() -> frozenset[str]:
    """Every attribute a fresh record carries, read off one so a new Python version cannot silently add one we miss."""
    probe = logging.LogRecord(name="", level=logging.NOTSET, pathname="", lineno=0, msg="", args=(), exc_info=None)
    # ``message`` and ``asctime`` are set by the formatter, not the constructor; ``makeRecord`` refuses them too.
    return frozenset({*vars(probe), "message", "asctime"})


STDLIB_LOG_RECORD_ATTRIBUTES: frozenset[str] = _stdlib_log_record_attributes()


def record_attribute_name(*, field_name: str) -> str:
    """The attribute a field lands on: its own name, or the prefixed one when the stdlib owns that name."""
    if field_name in STDLIB_LOG_RECORD_ATTRIBUTES:
        return f"{COLLIDING_FIELD_PREFIX}{field_name}"
    return field_name


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
        for field_name, value in fields.items():
            extra[record_attribute_name(field_name=field_name)] = value
    if data is not None:
        extra[DATA_FIELD] = data
    return extra
