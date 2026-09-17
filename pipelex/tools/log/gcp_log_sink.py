"""The ``gcp`` sink: Google Cloud Logging through the client library, one ``LogEntry`` per record.

Each record becomes one struct entry: the level maps onto the Cloud Logging severity scale, the
message and the call's fields become the JSON payload, the run-scoped identifiers become labels, and
the run's OpenTelemetry trace id becomes the entry's ``trace`` field, so Cloud Logging files the line
under the same trace as the spans the runtime exports. The entries leave through the client library's
transport, a batching background thread in production, so no record costs an API round trip on the
thread that logged it.

**Most processes should not select this sink.** A process on Cloud Run, on GKE, or on any platform
whose logging agent reads the container's stdout needs no client at all: the agent ingests one JSON
object per line with a ``severity`` and a ``message``, which is exactly what the ``json`` sink emits,
and the entries arrive in Cloud Logging with none of this sink's dependencies installed. Select
``gcp`` for a process that must write to Cloud Logging directly — one with no ingesting agent in
front of it, or one writing to a log or a project that is not the ambient one.

The client library is imported when the sink is built and nowhere else in this module, so a process
on another sink never loads it, and one selecting this sink without the extra fails at boot with
``MissingDependencyError`` naming ``pipelex[gcp-logging]``.
"""

from __future__ import annotations

import json
import logging
import math
import traceback
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol, cast

from typing_extensions import override

from pipelex.system.exceptions import MissingDependencyError
from pipelex.tools.log.log_context import PIPE_RUN_ID_FIELD, PIPELINE_RUN_ID_FIELD, REQUEST_ID_FIELD
from pipelex.tools.log.log_fields import COLLIDING_FIELD_PREFIX, carried_attributes
from pipelex.tools.log.log_sink import LogSink, LogSinkMethod, render_json
from pipelex.tools.misc.hash_utils import hash_md5_to_int

if TYPE_CHECKING:
    from pipelex.tools.log.log_config import GcpLogSinkConfig

# The dependency the ``gcp-logging`` extra installs, and the extra's own name, as the install hint spells them.
GCP_LOGGING_DEPENDENCY_NAME = "google-cloud-logging"
GCP_LOGGING_EXTRA_NAME = "gcp-logging"

# The payload keys the sink writes itself, spelled as the ``json`` sink spells them so one field keeps
# one wire name whichever of the two a process selects. A carried attribute named like one of them is
# prefixed rather than dropped.
MESSAGE_KEY = "message"
LOGGER_KEY = "logger"
EXCEPTION_KEY = "exception"
FIXED_PAYLOAD_KEYS = frozenset({MESSAGE_KEY, LOGGER_KEY, EXCEPTION_KEY})

# The record attributes that become entry labels rather than payload keys: the run-scoped identifiers
# the log context binds. Cloud Logging indexes labels, so these are what a query filters a run by.
LABEL_ATTRIBUTES = (REQUEST_ID_FIELD, PIPELINE_RUN_ID_FIELD, PIPE_RUN_ID_FIELD)


class GcpLogSeverity(StrEnum):
    """The Cloud Logging severities this sink writes. The API takes the name and uppercases it."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class GcpLogTransport(Protocol):
    """What this sink needs of a Cloud Logging transport: send one entry, flush, close.

    Declared here rather than imported from the client library, so this module loads without the
    library installed and so the sink's own call sites are typed. ``send`` keeps the library's
    positional signature because it is the library's shape and not ours to choose: the shipped
    implementation *is* its ``BackgroundThreadTransport``, and a test substitutes a capture.
    """

    def send(  # kw-only: ignore — the client library's own ``Transport.send`` signature, not ours to choose
        self,
        record: logging.LogRecord,
        message: dict[str, Any],
        **kwargs: Any,
    ) -> None: ...

    def flush(self) -> None: ...

    def close(self) -> None: ...


def severity_for_level(*, levelno: int) -> GcpLogSeverity:
    """The Cloud Logging severity for a stdlib level.

    Cloud Logging's scale is coarser than ours and has nothing below ``DEBUG``, so both of our custom
    levels land there: ``VERBOSE`` and ``DEV`` sit below ``INFO``, which is the whole of what the
    severity can say about them.
    """
    if levelno < logging.INFO:
        return GcpLogSeverity.DEBUG
    if levelno < logging.WARNING:
        return GcpLogSeverity.INFO
    if levelno < logging.ERROR:
        return GcpLogSeverity.WARNING
    if levelno < logging.CRITICAL:
        return GcpLogSeverity.ERROR
    return GcpLogSeverity.CRITICAL


def trace_name_for_run(*, project: str, pipeline_run_id: str) -> str:
    """The fully qualified Cloud Logging trace name for one pipeline run.

    The trace id is derived from the pipeline run id exactly as the tracer derives it, by the same
    hash, so a line and the spans of the run it belongs to carry one id without either having to
    reach the other. Cloud Logging wants that id project-qualified and as 32 hex digits.
    """
    return f"projects/{project}/traces/{hash_md5_to_int(pipeline_run_id):032x}"


def _payload_value(*, value: Any) -> Any:
    """The value as a Cloud Logging struct payload can carry it.

    A string, a bool, an int, a finite float and ``None`` ride as they are. Everything else — a
    mapping, a sequence, a model, a non-finite float, an object JSON refuses outright — goes through
    the wire renderer and comes back as whatever JSON made of it, so the payload is always something
    the client library can turn into a protobuf value and a serialization failure never costs the line.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    return json.loads(render_json(value=value))


def _exception_text(*, record: logging.LogRecord) -> str | None:
    """The record's exception as text, or ``None`` when it carries none."""
    if record.exc_text:
        return record.exc_text
    if record.exc_info is None:
        return None
    exc_type, exc_value, exc_traceback = record.exc_info
    if exc_type is None:
        return None
    return "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))


def _entry_payload(*, record: logging.LogRecord) -> dict[str, Any]:
    """The struct payload for one record: the message, the logger, the exception, then the fields.

    The run-scoped identifiers are left out: they are the entry's labels. Everything else the call,
    the record factory or the structured content attached rides flat beside the fixed keys, under a
    ``field_`` prefix when its name is one of them.
    """
    payload: dict[str, Any] = {
        MESSAGE_KEY: record.getMessage(),
        LOGGER_KEY: record.name,
    }
    exception_text = _exception_text(record=record)
    if exception_text is not None:
        payload[EXCEPTION_KEY] = exception_text
    for name, value in carried_attributes(record=record).items():
        if name in LABEL_ATTRIBUTES:
            continue
        key = name
        while key in payload or key in FIXED_PAYLOAD_KEYS:
            key = f"{COLLIDING_FIELD_PREFIX}{key}"
        payload[key] = _payload_value(value=value)
    return payload


def _entry_labels(*, record: logging.LogRecord) -> dict[str, str]:
    """The entry's labels: the run-scoped identifiers the record carries, as text, and only the ones it has."""
    labels: dict[str, str] = {}
    for name in LABEL_ATTRIBUTES:
        value = getattr(record, name, None)
        if value is not None:
            labels[name] = value if isinstance(value, str) else str(value)
    return labels


class GcpLogHandler(logging.Handler):
    """Translates each stdlib record into one Cloud Logging entry and hands it to the transport."""

    def __init__(self, *, transport: GcpLogTransport, project: str) -> None:
        super().__init__(level=logging.NOTSET)
        self._transport = transport
        self._project = project

    @override
    def emit(self, record: logging.LogRecord) -> None:
        try:
            pipeline_run_id = getattr(record, PIPELINE_RUN_ID_FIELD, None)
            trace = trace_name_for_run(project=self._project, pipeline_run_id=pipeline_run_id) if isinstance(pipeline_run_id, str) else None
            self._transport.send(
                record,
                _entry_payload(record=record),
                severity=severity_for_level(levelno=record.levelno).value,
                labels=_entry_labels(record=record),
                trace=trace,
            )
        except Exception:  # ruff: ignore[blind-except]
            # The stdlib's own contract for a handler: report through ``handleError`` and never raise
            # out of the log call.
            self.handleError(record)

    @override
    def flush(self) -> None:
        self._transport.flush()

    @override
    def close(self) -> None:
        self._transport.close()
        super().close()


class GcpLogSink(LogSink):
    """Google Cloud Logging behind one transport, a batching background thread in production.

    The transport and the project are resolved before the sink is built, so the sink itself imports
    nothing and a test builds it around a capture.
    """

    def __init__(self, *, transport: GcpLogTransport, project: str) -> None:
        super().__init__()
        self._transport = transport
        self._project = project

    @override
    def make_handler(self) -> logging.Handler:
        return GcpLogHandler(transport=self._transport, project=self._project)


def make_gcp_log_sink(*, config: GcpLogSinkConfig) -> GcpLogSink:
    """Build the sink that writes to Cloud Logging through the client library's background thread.

    Where the dependency is paid for: the client library is imported here, so a process that selected
    another sink never loads it, and one that selected this sink without the extra fails here, at
    boot, with the extra and the ``json`` alternative named.

    Raises:
        MissingDependencyError: If ``google-cloud-logging`` is not installed.

    """
    try:
        from google.cloud import logging as cloud_logging  # ruff: ignore[import-outside-top-level]
        from google.cloud.logging_v2.handlers.transports import (  # ruff: ignore[import-outside-top-level]
            BackgroundThreadTransport,
        )
    except ImportError as exc:
        msg = (
            f"The '{LogSinkMethod.GCP}' log sink writes to Google Cloud Logging through the client library. "
            f"Install the extra, or select the '{LogSinkMethod.JSON}' sink in [runtime.log]: a process whose "
            "platform runs a logging agent over its stdout, on Cloud Run or on GKE, needs no client at all, "
            "because that agent ingests the JSON objects that sink writes."
        )
        raise MissingDependencyError(
            dependency_name=GCP_LOGGING_DEPENDENCY_NAME,
            extra_name=GCP_LOGGING_EXTRA_NAME,
            message=msg,
        ) from exc

    client: Any
    if config.credentials_file_path is not None:
        client = cloud_logging.Client.from_service_account_json(  # pyright: ignore[reportUnknownMemberType]
            config.credentials_file_path,
            project=config.project_id,
        )
    else:
        client = cloud_logging.Client(project=config.project_id)
    transport = cast("GcpLogTransport", BackgroundThreadTransport(client, config.log_name))
    return GcpLogSink(transport=transport, project=str(client.project))
