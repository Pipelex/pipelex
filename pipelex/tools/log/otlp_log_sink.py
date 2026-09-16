"""The ``otlp`` sink: the OpenTelemetry logs signal, so a collector receives logs beside the spans.

Each record becomes one OTel log record on the logger named after the emitting module: the message
is the body, the level maps onto the OTel severity scale, the record's fields, context identifiers and
``data`` ride as attributes, with a value the wire cannot carry as is written as JSON text, and an
exception lands under the ``exception.*`` semantic-convention keys. This module imports the
OpenTelemetry SDK at load, which is why the built-in plugin imports it inside the ``otlp`` factory and
nowhere else.
"""

from __future__ import annotations

import logging
import traceback
from time import time_ns
from typing import TYPE_CHECKING, Any

from opentelemetry._logs import SeverityNumber  # ruff: ignore[import-private-name]
from opentelemetry.context import get_current
from opentelemetry.sdk._logs import LoggerProvider  # ruff: ignore[import-private-name]
from opentelemetry.semconv._incubating.attributes import code_attributes  # ruff: ignore[import-private-name]
from opentelemetry.semconv.attributes import exception_attributes
from typing_extensions import override

from pipelex.tools.log.log_fields import carried_attributes
from pipelex.tools.log.log_levels import LOGGING_LEVEL_DEV, LOGGING_LEVEL_VERBOSE
from pipelex.tools.log.log_sink import LogSink, render_json

if TYPE_CHECKING:
    from opentelemetry.sdk._logs import LogRecordProcessor as OTelLogRecordProcessor
    from opentelemetry.sdk.resources import Resource

# The loggers the OpenTelemetry SDK and its exporters write to. A record from one of them must not be
# exported through the pipeline that emitted it: an export failure would log, be exported, fail, and
# log again, and a shutdown waiting on the exporter thread would deadlock on this handler's lock.
OTEL_LOGGER_PREFIX = "opentelemetry"

_ATTRIBUTE_SCALAR_TYPES = (str, bool, int, float)


def _severity_number(*, levelno: int) -> SeverityNumber:
    """The OTel severity for a stdlib level, our two custom levels placed where they sit on ours."""
    if levelno <= LOGGING_LEVEL_VERBOSE:
        return SeverityNumber.TRACE
    if levelno < LOGGING_LEVEL_DEV:
        return SeverityNumber.DEBUG
    if levelno < logging.INFO:
        return SeverityNumber.DEBUG4
    if levelno < logging.WARNING:
        return SeverityNumber.INFO
    if levelno < logging.ERROR:
        return SeverityNumber.WARN
    if levelno < logging.CRITICAL:
        return SeverityNumber.ERROR
    return SeverityNumber.FATAL


def _severity_text(*, levelname: str) -> str:
    """The OTel display spelling: ``WARN`` for the stdlib's ``WARNING``, every other name as is."""
    return "WARN" if levelname == "WARNING" else levelname


def _attribute_value(*, value: Any) -> Any:
    """A value the OTel attribute model carries as is, or its JSON text when it does not."""
    if isinstance(value, _ATTRIBUTE_SCALAR_TYPES):
        return value
    if isinstance(value, (list, tuple)) and all(isinstance(item, _ATTRIBUTE_SCALAR_TYPES) for item in value):  # pyright: ignore[reportUnknownVariableType]
        return list(value)  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
    return render_json(value=value)


class OtlpLogHandler(logging.Handler):
    """Translates each stdlib record into an OTel log record and emits it on the provider's logger."""

    def __init__(self, *, logger_provider: LoggerProvider) -> None:
        super().__init__(level=logging.NOTSET)
        self._logger_provider = logger_provider

    @override
    def emit(self, record: logging.LogRecord) -> None:
        if record.name == OTEL_LOGGER_PREFIX or record.name.startswith(f"{OTEL_LOGGER_PREFIX}."):
            return
        try:
            logger = self._logger_provider.get_logger(record.name)
            logger.emit(
                timestamp=int(record.created * 1e9),
                observed_timestamp=time_ns(),
                context=get_current() or None,
                severity_text=_severity_text(levelname=record.levelname),
                severity_number=_severity_number(levelno=record.levelno),
                body=record.getMessage(),
                attributes=self._attributes(record=record),
            )
        except Exception:  # ruff: ignore[blind-except]
            # The stdlib's own contract for a handler: report through ``handleError`` and never raise
            # out of the log call.
            self.handleError(record)

    @override
    def flush(self) -> None:
        self._logger_provider.force_flush()

    @override
    def close(self) -> None:
        self._logger_provider.shutdown()
        super().close()

    @staticmethod
    def _attributes(*, record: logging.LogRecord) -> dict[str, Any]:
        attributes: dict[str, Any] = {name: _attribute_value(value=value) for name, value in carried_attributes(record=record).items()}
        attributes[code_attributes.CODE_FILE_PATH] = record.pathname
        attributes[code_attributes.CODE_FUNCTION_NAME] = record.funcName
        attributes[code_attributes.CODE_LINE_NUMBER] = record.lineno
        if record.exc_info:
            exc_type, exc_value, exc_traceback = record.exc_info
            if exc_type is not None:
                attributes[exception_attributes.EXCEPTION_TYPE] = exc_type.__name__
            if exc_value is not None:
                attributes[exception_attributes.EXCEPTION_MESSAGE] = str(exc_value)
            if exc_traceback is not None:
                attributes[exception_attributes.EXCEPTION_STACKTRACE] = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        return attributes


class OtlpLogSink(LogSink):
    """The OpenTelemetry logs signal behind one log record processor, a batching exporter in production."""

    def __init__(self, *, processor: OTelLogRecordProcessor, resource: Resource | None = None) -> None:
        super().__init__()
        self._logger_provider = LoggerProvider(resource=resource)
        self._logger_provider.add_log_record_processor(processor)

    @property
    def logger_provider(self) -> LoggerProvider:
        return self._logger_provider

    @override
    def make_handler(self) -> logging.Handler:
        return OtlpLogHandler(logger_provider=self._logger_provider)
