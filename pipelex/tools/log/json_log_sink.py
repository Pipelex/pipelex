"""The ``json`` sink: one JSON object per line on the configured stream, and no ANSI ever.

The keys are the ones a log agent ingests without a parser, the CloudWatch agent, the Google Cloud
Logging agent and any OTLP collector among them: ``time``, ``severity``, ``logger``, ``message``, then
``exception`` when the record carries one, then ``trace_id``, ``span_id`` and ``trace_flags`` when the
record was logged inside a valid span, then the fields, the context identifiers and the ``data``
attribute under their own names. The trace keys are the ones OpenTelemetry specifies for trace context
in a JSON log that is not OTLP, hex-encoded, so a collector or an error tracker joins the line to its
trace without a parser. They are read from OpenTelemetry's current span when the record is formatted,
which the stream handler does inside the log call, in the calling task; a boot line held until the sink
arrives is formatted when the boot installs the sink. The sink's own keys, the trace keys among them,
are reserved whether or not the line carries them: a field named like one is carried under the same
``field_`` prefix the record uses for a name the stdlib owns, on every line and not only the ones with
an exception or a span, so no value is lost and a field keeps one wire name. A non-finite float is written as the string ``"NaN"``, ``"Infinity"`` or
``"-Infinity"``, since JSON has no token for it that a strict parser accepts.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from opentelemetry import trace
from typing_extensions import override

from pipelex.tools.log.log_fields import COLLIDING_FIELD_PREFIX, carried_attributes
from pipelex.tools.log.log_sink import LogSink, json_fallback, spell_non_finite

if TYPE_CHECKING:
    from typing import TextIO

TIME_KEY = "time"
SEVERITY_KEY = "severity"
LOGGER_KEY = "logger"
MESSAGE_KEY = "message"
EXCEPTION_KEY = "exception"
TRACE_ID_KEY = "trace_id"
SPAN_ID_KEY = "span_id"
TRACE_FLAGS_KEY = "trace_flags"
# The keys the sink writes itself, reserved on every line; a carried attribute of the same name is prefixed.
FIXED_KEYS = frozenset({TIME_KEY, SEVERITY_KEY, LOGGER_KEY, MESSAGE_KEY, EXCEPTION_KEY, TRACE_ID_KEY, SPAN_ID_KEY, TRACE_FLAGS_KEY})


def _json_line(*, payload: dict[str, Any]) -> str:
    """One JSON object for the payload, never raising and never anything but an object.

    A model dumps in JSON mode and an unknown object becomes its text. When ``json`` refuses the
    payload outright, a circular reference or a mapping with a non-string key inside a carried value,
    every carried value is written as its ``repr`` and the line keeps its shape: a sink must render
    every record it is handed, and a serialization failure is a fact about the value, never a reason to
    lose the line or to break the one-object-per-line contract.
    """
    try:
        return json.dumps(payload, ensure_ascii=False, allow_nan=False, default=json_fallback)
    except (TypeError, ValueError):
        safe_payload = {key: value if key in FIXED_KEYS else repr(value) for key, value in payload.items()}
        return json.dumps(safe_payload, ensure_ascii=False, default=str)


def _current_trace_context() -> dict[str, str]:
    """The current span's trace context under the OpenTelemetry JSON keys, or nothing outside a valid span."""
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return {}
    return {
        TRACE_ID_KEY: trace.format_trace_id(span_context.trace_id),
        SPAN_ID_KEY: trace.format_span_id(span_context.span_id),
        TRACE_FLAGS_KEY: f"{span_context.trace_flags:02x}",
    }


def _iso_utc(*, created: float) -> str:
    """The record's creation time as ISO 8601 in UTC with millisecond precision and a ``Z`` suffix."""
    return datetime.fromtimestamp(created, tz=UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class JsonLogFormatter(logging.Formatter):
    """Renders a record as one JSON object, its carried attributes flat beside the fixed keys."""

    @override
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            TIME_KEY: _iso_utc(created=record.created),
            SEVERITY_KEY: record.levelname,
            LOGGER_KEY: record.name,
            MESSAGE_KEY: record.getMessage(),
        }
        if record.exc_info:
            payload[EXCEPTION_KEY] = record.exc_text or self.formatException(record.exc_info)
        elif record.exc_text:
            payload[EXCEPTION_KEY] = record.exc_text
        payload.update(_current_trace_context())
        for name, value in carried_attributes(record=record).items():
            key = name
            while key in payload or key in FIXED_KEYS:
                key = f"{COLLIDING_FIELD_PREFIX}{key}"
            payload[key] = spell_non_finite(value=value)
        return _json_line(payload=payload)


class JsonLogSink(LogSink):
    """One JSON object per line on a text stream."""

    def __init__(self, *, stream: TextIO) -> None:
        super().__init__()
        self._stream = stream
        self._stream_handler: logging.StreamHandler[TextIO] | None = None

    @override
    def make_handler(self) -> logging.Handler:
        handler: logging.StreamHandler[TextIO] = logging.StreamHandler(self._stream)
        handler.setFormatter(JsonLogFormatter())
        self._stream_handler = handler
        return handler

    @override
    def redirect_to_stderr(self) -> None:
        if self._stream_handler is None:
            _ = self.handler
        if self._stream_handler is not None:
            self._stream_handler.setStream(sys.stderr)
