"""The ``json`` sink: one JSON object per line on the configured stream, and no ANSI ever.

The keys are the ones a log agent ingests without a parser, the CloudWatch agent, the Google Cloud
Logging agent and any OTLP collector among them: ``time``, ``severity``, ``logger``, ``message``, then
``exception`` when the record carries one, then the fields, the context identifiers and the ``data``
attribute under their own names. A field named like one of the sink's own keys is carried under the
same ``field_`` prefix the record uses for a name the stdlib owns, so no value is lost.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from typing_extensions import override

from pipelex.tools.log.log_fields import COLLIDING_FIELD_PREFIX, carried_attributes
from pipelex.tools.log.log_sink import LogSink, json_fallback

if TYPE_CHECKING:
    from typing import TextIO

TIME_KEY = "time"
SEVERITY_KEY = "severity"
LOGGER_KEY = "logger"
MESSAGE_KEY = "message"
EXCEPTION_KEY = "exception"
# The keys the sink writes itself; a carried attribute of the same name is prefixed.
FIXED_KEYS = frozenset({TIME_KEY, SEVERITY_KEY, LOGGER_KEY, MESSAGE_KEY, EXCEPTION_KEY})


def _json_line(*, payload: dict[str, Any]) -> str:
    """One JSON object for the payload, never raising and never anything but an object.

    A model dumps in JSON mode and an unknown object becomes its text. When ``json`` refuses the
    payload outright, a circular reference or a mapping with a non-string key inside a carried value,
    every carried value is written as its ``repr`` and the line keeps its shape: a sink must render
    every record it is handed, and a serialization failure is a fact about the value, never a reason to
    lose the line or to break the one-object-per-line contract.
    """
    try:
        return json.dumps(payload, ensure_ascii=False, default=json_fallback)
    except (TypeError, ValueError):
        safe_payload = {key: value if key in FIXED_KEYS else repr(value) for key, value in payload.items()}
        return json.dumps(safe_payload, ensure_ascii=False, default=str)


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
        for name, value in carried_attributes(record=record).items():
            key = name
            while key in payload:
                key = f"{COLLIDING_FIELD_PREFIX}{key}"
            payload[key] = value
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
