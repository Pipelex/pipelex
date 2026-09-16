"""The ``otlp`` sink: the OpenTelemetry logs signal, so a collector receives logs beside the spans.

Each record becomes one OTel log record on the logger named after the emitting module: the message
is the body, the level maps onto the OTel severity scale, the record's fields, context identifiers and
``data`` ride as attributes, with a value the wire cannot carry as is written as JSON text, and an
exception lands under the ``exception.*`` semantic-convention keys. The records the sink's own export
path emits, the SDK's and the transport's, are rejected by a filter on the handler and never
exported. This module imports the OpenTelemetry SDK at load, which is why the built-in plugin imports
it inside the ``otlp`` factory and nowhere else.
"""

from __future__ import annotations

import logging
import traceback
from time import time_ns
from typing import TYPE_CHECKING, Any, cast

from opentelemetry._logs import SeverityNumber  # ruff: ignore[import-private-name]
from opentelemetry.context import (
    _SUPPRESS_INSTRUMENTATION_KEY,  # ruff: ignore[import-private-name] # pyright: ignore[reportPrivateUsage]
    get_current,
    get_value,
)
from opentelemetry.sdk._logs import LoggerProvider  # ruff: ignore[import-private-name]
from opentelemetry.semconv._incubating.attributes import code_attributes  # ruff: ignore[import-private-name]
from opentelemetry.semconv.attributes import exception_attributes
from typing_extensions import override

from pipelex.tools.log.log_fields import carried_attributes
from pipelex.tools.log.log_levels import LOGGING_LEVEL_DEV, LOGGING_LEVEL_VERBOSE
from pipelex.tools.log.log_sink import LogSink, render_json

if TYPE_CHECKING:
    from collections.abc import Sequence

    from opentelemetry.sdk._logs import LogRecordProcessor as OTelLogRecordProcessor
    from opentelemetry.sdk.resources import Resource

# The loggers the OpenTelemetry SDK and its exporters write to. A record from one of them must not be
# exported through the pipeline that emitted it: an export failure would log, be exported, fail, and
# log again.
OTEL_LOGGER_PREFIX = "opentelemetry"

# The deadline a flush hands the provider. The SDK's batch processor discards it today and waits on
# its export lock unbounded, so the bound a flush actually has is the exporter's own timeout,
# ``OTEL_EXPORTER_OTLP_TIMEOUT``; the value is passed for the SDK version that honours it.
FLUSH_TIMEOUT_MILLIS = 5000

_ATTRIBUTE_SCALAR_TYPES = (str, bool, int, float)


class ExportPathFilter(logging.Filter):
    """Rejects the records the sink's own export path emits, before the handler's lock is taken.

    Two guards. The SDK's and the exporters' loggers are named ``opentelemetry.*`` and are rejected by
    name. The transport beneath the exporter, ``requests`` and ``urllib3`` for the HTTP one, logs under
    its own names, so the second guard reads the context value the SDK's batch processor attaches
    around ``exporter.export`` and rejects any record emitted while it is set: the records of an export
    in flight, on the exporting thread, whatever the transport is called. That key is a private SDK
    name; the test against the installed SDK is what pins it.

    A filter rather than a check inside ``emit``, because ``Handler.handle`` runs the filters before it
    takes the handler's lock and ``emit`` after. A guard in ``emit`` still let an exporting thread block
    on this lock to report its failure while ``logging.shutdown`` held it and waited for the export
    lock: a deadlock at exit, reproduced with the installed SDK.
    """

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == OTEL_LOGGER_PREFIX or record.name.startswith(f"{OTEL_LOGGER_PREFIX}."):
            return False
        return not get_value(_SUPPRESS_INSTRUMENTATION_KEY)


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
    """A value the OTel attribute model carries as is, or its JSON text when it does not.

    The SDK drops a sequence whose elements are not all of one scalar type, and it compares types by
    equality, so ``[1, True]`` is mixed to it: the same test here, and JSON text for what would be dropped.
    """
    if isinstance(value, _ATTRIBUTE_SCALAR_TYPES):
        return value
    if isinstance(value, (list, tuple)):
        items: list[Any] = list(cast("Sequence[Any]", value))
        element_types: set[type[Any]] = {type(item) for item in items}
        if not items or (len(element_types) == 1 and next(iter(element_types)) in _ATTRIBUTE_SCALAR_TYPES):
            return items
    return render_json(value=value)


class OtlpLogHandler(logging.Handler):
    """Translates each stdlib record into an OTel log record and emits it on the provider's logger."""

    def __init__(self, *, logger_provider: LoggerProvider) -> None:
        super().__init__(level=logging.NOTSET)
        self._logger_provider = logger_provider

    @override
    def emit(self, record: logging.LogRecord) -> None:
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
        self._logger_provider.force_flush(timeout_millis=FLUSH_TIMEOUT_MILLIS)

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
        handler = OtlpLogHandler(logger_provider=self._logger_provider)
        handler.addFilter(ExportPathFilter())
        return handler
