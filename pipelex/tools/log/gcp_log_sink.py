"""The ``gcp`` sink: Google Cloud Logging through the client library, one ``LogEntry`` per record.

Each record becomes one struct entry: the level maps onto the Cloud Logging severity scale, the
message and the call's fields become the JSON payload, the run-scoped identifiers become labels, and
OpenTelemetry's current span, the host's own, which is only read, becomes the entry's ``trace``,
``spanId`` and ``traceSampled``, so Cloud Logging files the line under the trace of the host's spans; a
line logged under no current span has none of the three. The Pipelex span held when the record was
logged, a pipe's or an LLM call's, rides in the payload as ``pipelex.trace_id`` and ``pipelex.span_id``,
in hex, exactly as the ``json`` sink writes it. The entries leave through the client library's
transport, a batching background thread in production, so no record costs an API round trip on the
thread that logged it. What that thread itself logs never leaves through the sink: the library reports
a refused batch through a logger of its own, and a report exported through the pipeline it reports on
fails with it and is reported again, so the handler rejects the export path before its lock is taken.

The credentials are refreshed once when the sink is built. Over gRPC, the library's default, a refresh
that fails surfaces as a retriable ``UNAVAILABLE``, so the transport retries the batch for a minute before
anything reports it, and a process that closes sooner loses every record without a word. The refresh at
boot is what says it instead: credentials Google refuses stop the boot naming them, and a refresh that
cannot get an answer is said on stderr. A flush that runs out of time at teardown says so too, naming
what a fresh refresh of the credentials answers, since that is the likeliest reason a write is held.

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
import threading
import time
from enum import StrEnum
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, NamedTuple, Protocol, cast

from opentelemetry import trace
from typing_extensions import override

from pipelex.system.exceptions import MissingDependencyError
from pipelex.system.telemetry.current_span import current_span_context_for_logs, pipelex_trace_fields_for_logs
from pipelex.tools.log.exceptions import GcpLogSinkCredentialsError
from pipelex.tools.log.json_log_sink import EXCEPTION_KEY, FIXED_KEYS, LOGGER_KEY, MESSAGE_KEY
from pipelex.tools.log.log_context import PIPE_RUN_ID_FIELD, PIPELINE_RUN_ID_FIELD, REQUEST_ID_FIELD
from pipelex.tools.log.log_fields import COLLIDING_FIELD_PREFIX, carried_attributes
from pipelex.tools.log.log_sink import LogSink, LogSinkMethod, render_json

if TYPE_CHECKING:
    from collections.abc import Callable

    from pipelex.tools.log.log_config import GcpLogSinkConfig

# The dependency the ``gcp-logging`` extra installs, and the extra's own name, as the install hint spells them.
GCP_LOGGING_DEPENDENCY_NAME = "google-cloud-logging"
GCP_LOGGING_EXTRA_NAME = "gcp-logging"

# The sink writes some of the ``json`` sink's keys into the payload — its ``message``, ``logger`` and
# ``exception``, and the ``pipelex.trace_id`` and ``pipelex.span_id`` of the held Pipelex span, all
# imported rather than respelled — and reserves that sink's whole set against a carried attribute, so one
# field keeps one wire name whichever of the two a process selects. ``time`` and ``severity`` are not
# payload keys here, the client library carrying both out of band, and neither are ``trace_id``,
# ``span_id`` and ``trace_flags``, the entry's own ``trace``, ``spanId`` and ``traceSampled`` carrying the
# current span, but a field named like one is ``field_time`` or ``field_trace_id`` under either sink
# rather than under one only.
FIXED_PAYLOAD_KEYS = FIXED_KEYS

# The stdlib formatter the ``json`` sink renders a traceback through, so both sinks spell one exception
# the same way: the trailing newline stripped, and the stdlib's own placeholder for the
# ``(None, None, None)`` triple a caller logging outside an ``except`` block produces.
_EXCEPTION_FORMATTER = logging.Formatter()

# The record attributes that become entry labels rather than payload keys: the run-scoped identifiers
# the log context binds. Cloud Logging indexes labels, so these are what a query filters a run by.
LABEL_ATTRIBUTES = (REQUEST_ID_FIELD, PIPELINE_RUN_ID_FIELD, PIPE_RUN_ID_FIELD)

# The client library's own logging loggers, and the name its transport gives the thread that exports.
# A record from either must not travel out through the sink that emitted it.
GCP_LOGGING_LOGGER_PREFIXES = ("google.cloud.logging", "google.cloud.logging_v2")
GCP_WORKER_THREAD_NAME = "google.cloud.logging.Worker"

# How often an export failure is printed on stderr. The library reports a refused batch once per failed
# commit and never retries it, so a refusal that persists — a missing permission, a revoked key — reports
# at the rate the application logs. The first report in a window is printed with its traceback, and the
# ones after it are counted and said in one line once the window has passed: with the next report, on
# the next record the handler sees, or when the handler closes, whichever comes first. The OpenTelemetry SDK
# deduplicates its own exporter's failures over the same window.
EXPORT_FAILURE_REPORT_INTERVAL_SECONDS = 20.0

# The deadline a flush waits for the transport's queue to drain. The client library's ``flush`` ends in
# ``queue.join()``, which waits unbounded and takes no timeout, so the bound is imposed here rather
# than passed: the drain runs on a thread of its own and the join is what carries the deadline. What is
# still queued when it expires leaves through ``close``, whose grace period the library bounds itself.
FLUSH_TIMEOUT_SECONDS = 5.0
_FLUSH_THREAD_NAME = "pipelex-gcp-log-flush"

# The deadline one refresh of the sink's credentials is given, at boot and again at teardown when a flush
# has run out of time. A refresh is one round trip to a token endpoint or to the metadata server, but the
# auth library's own request timeout is two minutes and its metadata client retries, so the bound is
# imposed the way the flush's is: the refresh runs on a thread of its own and the join carries it.
CREDENTIALS_CHECK_TIMEOUT_SECONDS = 5.0
_CREDENTIALS_CHECK_THREAD_NAME = "pipelex-gcp-log-credentials"


def _print_record_on_stderr(*, record: logging.LogRecord) -> None:
    """Print a record the sink rejected on stderr, through the stdlib's last-resort handler, which never takes the sink's lock."""
    stderr_handler = logging.lastResort
    if stderr_handler is not None:
        stderr_handler.handle(record)


def _say_on_stderr(*, message: str) -> None:
    """Print one warning of the sink's own on stderr, through the stdlib's last-resort handler.

    What the sink says about itself cannot go through the sink: at boot it is not installed yet, and
    when its writes are refused, a line exported through it is lost with the rest. The last resort
    takes its own lock and never the handler's, so saying it cannot deadlock the teardown either.
    """
    _print_record_on_stderr(
        record=logging.makeLogRecord(
            {
                "name": __name__,
                "levelno": logging.WARNING,
                "levelname": logging.getLevelName(logging.WARNING),
                "msg": message,
            }
        )
    )


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


class GcpExportPathFilter(logging.Filter):
    """Rejects the records the sink's own export path emits, before the handler's lock is taken.

    Two guards. The client library's logging loggers are named ``google.cloud.logging*`` and are
    rejected by name: its transport reports a failed batch through one of them, at ``ERROR``, and
    nothing sets ``propagate = False`` on it — the library does that in its own ``setup_logging``,
    which this sink deliberately does not call. Left to reach the handler, that report becomes an entry,
    fails with the batch it reports on, and is reported again, forever. The second guard rejects every
    record emitted on the transport's background thread, whatever its logger is called, which is what
    catches the layers beneath: the auth stack and the HTTP or gRPC client log under their own names
    and only ever reach this handler from that thread, the transport's ``send`` being the one call the
    sink makes and the export being the one thing that thread does. Both names are the library's own,
    and the tests against the installed library are what pin them.

    A filter rather than a check inside ``emit``, because ``Handler.handle`` runs the filters before it
    takes the handler's lock and ``emit`` after. The ``otlp`` sink carries the same design for the same
    reason: an exporting thread blocking on that lock to report its own failure while the teardown holds
    it and waits for the queue to drain is a deadlock at exit, and it was reproduced here with the
    installed library.

    The sink's own credentials check is guarded the same way, by the name of its thread. At teardown it
    runs while the flush that started it waits, and the stdlib's shutdown at exit holds this handler's
    lock around that flush, so a warning the auth library logs during the refresh would wait on the lock
    until the check's deadline passed and the check would answer that the refresh did not answer. What
    that thread logs is printed on stderr through the last resort, every line of it: it is not an export
    failure, and the check logs a handful of lines at most.

    A rejected record at ``WARNING`` or above is printed on stderr through the stdlib's last-resort
    handler rather than dropped. The library reports a refused batch only through that record and then
    marks the batch done, so a flush still succeeds, and the stdlib prints a record through its last
    resort only when no handler is found, which the sink's handler always is: without this, a process
    whose writes Cloud Logging refuses would lose every line and say nothing anywhere. The last resort
    takes its own lock and never this handler's, so the report cannot reintroduce the deadlock, and the
    reports are rate-limited by ``EXPORT_FAILURE_REPORT_INTERVAL_SECONDS``.
    """

    def __init__(self, *, report_interval_seconds: float = EXPORT_FAILURE_REPORT_INTERVAL_SECONDS) -> None:
        super().__init__()
        self._report_interval_seconds = report_interval_seconds
        self._report_lock = threading.Lock()
        self._last_report_at: float | None = None
        self._unreported_count = 0

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        if threading.current_thread().name == _CREDENTIALS_CHECK_THREAD_NAME:
            if record.levelno >= logging.WARNING:
                _print_record_on_stderr(record=record)
            return False
        if not self._is_export_path(record=record):
            # Read outside the lock, which keeps an ordinary record's cost to this one read: a count it
            # misses is said on a later record, or when the handler closes.
            if self._unreported_count:
                self._report_count_once_its_window_has_passed()
            return True
        if record.levelno >= logging.WARNING:
            self._report_on_stderr(record=record)
        return False

    def report_unreported(self) -> None:
        """Print the failures counted and not yet printed, whatever the window: the handler's last word at close."""
        with self._report_lock:
            unreported_count = self._unreported_count
            self._unreported_count = 0
        self._print_unreported_count(unreported_count=unreported_count)

    @classmethod
    def _is_export_path(cls, *, record: logging.LogRecord) -> bool:
        if threading.current_thread().name == GCP_WORKER_THREAD_NAME:
            return True
        return any(record.name == prefix or record.name.startswith(f"{prefix}.") for prefix in GCP_LOGGING_LOGGER_PREFIXES)

    def _report_on_stderr(self, *, record: logging.LogRecord) -> None:
        """Print the export path's report through the last resort, the first one per window in full."""
        now = time.monotonic()
        with self._report_lock:
            if self._window_is_open(now=now):
                self._unreported_count += 1
                return
            self._last_report_at = now
            unreported_count = self._unreported_count
            self._unreported_count = 0
        self._print_unreported_count(unreported_count=unreported_count)
        _print_record_on_stderr(record=record)

    def _report_count_once_its_window_has_passed(self) -> None:
        """Print the count an outage that has ended left behind, since no later failure comes to print it.

        The window is left as it is: the count is one line, and a failure arriving next is still printed
        in full rather than counted.
        """
        with self._report_lock:
            if self._window_is_open(now=time.monotonic()):
                return
            unreported_count = self._unreported_count
            self._unreported_count = 0
        self._print_unreported_count(unreported_count=unreported_count)

    def _window_is_open(self, *, now: float) -> bool:
        return self._last_report_at is not None and now - self._last_report_at < self._report_interval_seconds

    @classmethod
    def _print_unreported_count(cls, *, unreported_count: int) -> None:
        if not unreported_count:
            return
        _say_on_stderr(message=f"The gcp log sink's transport reported {unreported_count} more export failures since the last one printed")


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


def trace_name(*, project: str, trace_id: int) -> str:
    """The fully qualified Cloud Logging trace name for an OpenTelemetry trace id: project-qualified, as 32 hex digits."""
    return f"projects/{project}/traces/{trace.format_trace_id(trace_id)}"


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
    """The record's exception as text, spelled as the ``json`` sink spells it, or ``None`` when it carries none.

    The rendering goes through the stdlib formatter rather than through ``traceback`` directly, so the
    two sinks cannot disagree about a traceback's trailing newline or about what an ``exc_info`` of
    ``(None, None, None)`` means — a triple ``logging.error(msg, exc_info=True)`` builds when a caller
    outside an ``except`` block asks for one, which a foreign library does.
    """
    if record.exc_info:
        return record.exc_text or _EXCEPTION_FORMATTER.formatException(record.exc_info)
    if record.exc_text:
        return record.exc_text
    return None


def _entry_payload(*, record: logging.LogRecord) -> dict[str, Any]:
    """The struct payload for one record: the message, the logger, the exception, the held Pipelex span, then the fields.

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
    payload.update(pipelex_trace_fields_for_logs())
    for name, value in carried_attributes(record=record).items():
        if name in LABEL_ATTRIBUTES:
            continue
        key = name
        while key in payload or key in FIXED_PAYLOAD_KEYS:
            key = f"{COLLIDING_FIELD_PREFIX}{key}"
        payload[key] = _payload_value(value=value)
    return payload


def _entry_trace_context(*, project: str) -> dict[str, Any]:
    """The entry's ``trace``, ``span_id`` and ``trace_sampled`` for OpenTelemetry's current span, or nothing when it names no trace.

    Passed to the transport as keyword arguments, which the client library's transport forwards to the
    entry it builds. Only ever the current span: a Pipelex span held here is the payload's, and a run
    with no current span is filed under no trace, its ``pipeline_run_id`` label being what selects it.
    """
    span_context = current_span_context_for_logs()
    if span_context is None:
        return {}
    return {
        "trace": trace_name(project=project, trace_id=span_context.trace_id),
        "span_id": trace.format_span_id(span_context.span_id),
        "trace_sampled": span_context.trace_flags.sampled,
    }


def _entry_labels(*, record: logging.LogRecord) -> dict[str, str]:
    """The entry's labels: the run-scoped identifiers the record carries, as text, and only the ones it has."""
    labels: dict[str, str] = {}
    for name in LABEL_ATTRIBUTES:
        value = getattr(record, name, None)
        if value is not None:
            labels[name] = value if isinstance(value, str) else str(value)
    return labels


class GcpCredentialsOutcome(StrEnum):
    """What one refresh of the sink's credentials came to."""

    REFRESHED = "refreshed"
    # Google answered and refused them: a revoked or expired refresh token, a deleted key, a machine
    # whose metadata server has no service account to hand out. Retrying does not change the answer.
    REFUSED = "refused"
    # The token endpoint or the metadata server could not be reached, or answered with a status that
    # says to retry: nothing is known about the credentials themselves.
    UNREACHABLE = "unreachable"
    # The refresh had not returned when its deadline passed.
    UNANSWERED = "unanswered"


class GcpCredentialsVerdict(NamedTuple):
    """The outcome of one refresh, with the exception it raised when it raised one."""

    outcome: GcpCredentialsOutcome
    failure: Exception | None = None


def describe_failure(*, failure: BaseException | None) -> str:
    """The exception's class and message, as the sink's lines quote it."""
    if failure is None:
        return "no exception"
    return f"{type(failure).__name__}: {failure}"


class GcpCredentialsCheck:
    """Refreshes the sink's credentials once, off the calling thread and within a deadline, and says what came of it.

    The refresh is the auth library's, handed in as a callable so this module imports none of it and a
    test substitutes its own. What tells an unreachable endpoint from a refusal is handed in the same way:
    the auth library's transport error types. A failure is ``UNREACHABLE`` when it, or an exception it was
    raised from, is one of them or declares itself retryable — the metadata-server credentials wrap a
    transport failure in the refusal type, so the class of the outermost exception is not enough — and
    ``REFUSED`` otherwise, an exception nobody anticipated included, because the boot it stops names it.
    A transport failure that carries a final answer is a refusal all the same: the metadata server
    answers a machine with no service account with a ``404``, and its client raises that as a transport
    error with the response attached rather than retry it.
    """

    def __init__(
        self,
        *,
        refresh: Callable[[], None],
        transport_error_types: tuple[type[Exception], ...],
        source: str,
    ) -> None:
        self._refresh = refresh
        self._transport_error_types = transport_error_types
        self._source = source

    @property
    def source(self) -> str:
        """Which credentials these are, as a sentence names them: the Application Default Credentials, or a key file."""
        return self._source

    def run(self) -> GcpCredentialsVerdict:
        """Refresh once and wait no longer than ``CREDENTIALS_CHECK_TIMEOUT_SECONDS`` for the answer.

        A refresh still running when the deadline passes is left to finish on its daemon thread, and
        whatever it answers then is not read: the verdict is ``UNANSWERED``.
        """
        verdicts: list[GcpCredentialsVerdict] = []

        def refresh_once() -> None:
            try:
                self._refresh()
            except Exception as exc:  # ruff: ignore[blind-except]
                # Unbounded code: the auth library's refresh, whose exceptions depend on the kind of credentials.
                # Nothing is swallowed: the failure is classified and handed back in the verdict.
                verdicts.append(GcpCredentialsVerdict(outcome=self._classify(failure=exc), failure=exc))
                return
            verdicts.append(GcpCredentialsVerdict(outcome=GcpCredentialsOutcome.REFRESHED))

        refreshing = threading.Thread(target=refresh_once, name=_CREDENTIALS_CHECK_THREAD_NAME, daemon=True)
        refreshing.start()
        refreshing.join(timeout=CREDENTIALS_CHECK_TIMEOUT_SECONDS)
        if not verdicts:
            return GcpCredentialsVerdict(outcome=GcpCredentialsOutcome.UNANSWERED)
        return verdicts[0]

    def _classify(self, *, failure: Exception) -> GcpCredentialsOutcome:
        """``UNREACHABLE`` when a transport failure is anywhere on the chain the traceback would print, ``REFUSED`` otherwise."""
        seen: set[int] = set()
        current: BaseException | None = failure
        while current is not None and id(current) not in seen:
            if isinstance(current, self._transport_error_types):
                if _carries_a_final_answer(failure=current):
                    return GcpCredentialsOutcome.REFUSED
                return GcpCredentialsOutcome.UNREACHABLE
            if getattr(current, "retryable", False) is True:
                return GcpCredentialsOutcome.UNREACHABLE
            seen.add(id(current))
            if current.__cause__ is not None:
                current = current.__cause__
            elif current.__suppress_context__:
                current = None
            else:
                current = current.__context__
        return GcpCredentialsOutcome.REFUSED


def _carries_a_final_answer(*, failure: BaseException) -> bool:
    """Whether a transport failure carries an HTTP answer that retrying does not change: a ``4xx`` other than a timeout or a rate limit.

    The auth library's metadata client raises its transport error with the response as the second
    argument when the server answers with a status it does not retry, and with none when the server
    could not be reached or its retries ran out; ``5xx``, ``408`` and ``429`` are the ones it retries.
    """
    if len(failure.args) < 2:
        return False
    status = getattr(failure.args[1], "status", None)
    if not isinstance(status, int):
        return False
    return HTTPStatus.BAD_REQUEST <= status < HTTPStatus.INTERNAL_SERVER_ERROR and not says_to_retry(status=status)


def says_to_retry(*, status: int) -> bool:
    """Whether an HTTP status from a credential endpoint says to retry: a ``5xx``, a timeout or a rate limit, the ones the auth library retries."""
    return status >= HTTPStatus.INTERNAL_SERVER_ERROR or status in {HTTPStatus.REQUEST_TIMEOUT, HTTPStatus.TOO_MANY_REQUESTS}


def _undelivered_message(*, cause: str | None) -> str:
    """What the sink says when its flush ran out of time, followed by the likeliest cause when one was found."""
    held = (
        f"The '{LogSinkMethod.GCP}' log sink's transport was still writing to Cloud Logging when the "
        f"{FLUSH_TIMEOUT_SECONDS:g}-second flush deadline passed, and the records it still holds are lost unless it sends them while it closes."
    )
    if cause is None:
        return held
    return f"{held} {cause}"


def _cause_from_refresh(*, source: str, verdict: GcpCredentialsVerdict) -> str:
    """What a refresh made once the flush ran out of time says about why the write is held."""
    match verdict.outcome:
        case GcpCredentialsOutcome.REFRESHED:
            return f"A refresh of {source} still succeeds, so the Cloud Logging API or the network is what holds the write."
        case GcpCredentialsOutcome.REFUSED:
            return f"A refresh of {source} is now refused, which is why: {describe_failure(failure=verdict.failure)}"
        case GcpCredentialsOutcome.UNREACHABLE:
            return f"A refresh of {source} cannot reach the credential endpoint either: {describe_failure(failure=verdict.failure)}"
        case GcpCredentialsOutcome.UNANSWERED:
            return f"A refresh of {source} did not answer within {CREDENTIALS_CHECK_TIMEOUT_SECONDS:g} seconds either."


class GcpLogHandler(logging.Handler):
    """Translates each stdlib record into one Cloud Logging entry and hands it to the transport."""

    def __init__(self, *, transport: GcpLogTransport, project: str, credentials_check: GcpCredentialsCheck | None = None) -> None:
        super().__init__(level=logging.NOTSET)
        self._transport = transport
        self._project = project
        self._credentials_check = credentials_check
        self._is_closed = False
        self._export_path_filter = GcpExportPathFilter()
        self.addFilter(self._export_path_filter)

    @override
    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._transport.send(
                record,
                _entry_payload(record=record),
                severity=severity_for_level(levelno=record.levelno).value,
                labels=_entry_labels(record=record),
                **_entry_trace_context(project=self._project),
            )
        except Exception:  # ruff: ignore[blind-except]
            # Unbounded code: a third-party SDK with no documented exception types, over values the caller attached.
            # The stdlib's own contract for a handler is to report through ``handleError`` and never raise
            # out of the log call.
            self.handleError(record)

    @override
    def flush(self) -> None:
        """Waits for the transport's queue to drain for ``FLUSH_TIMEOUT_SECONDS`` at most, then says so when it did not.

        The library's own flush waits on the queue with no deadline, and the teardown that calls it runs
        in a ``finally``: a batch the API is refusing, or an export the network is holding, would keep
        the process alive with no way out. The drain is given a thread so the join can carry the bound,
        and a failure it raises is re-raised here so the teardown still reports it.

        A drain still running when the deadline passes is said on stderr rather than left to the
        library's close, whose only line counts what is still queued and names no reason: the sink
        refreshes its credentials once more and says what that answered, since a refresh the gRPC
        transport keeps retrying is the likeliest reason a write is held. That refresh has its own
        deadline, ``CREDENTIALS_CHECK_TIMEOUT_SECONDS``, so a flush that runs out of time returns within
        the sum of the two. The transport's worker goes on sending meanwhile, so the wait costs no record.

        After ``close`` it does nothing. The stdlib's shutdown at exit flushes every handler still
        alive, and a drain left running holds this one alive, so without that it would wait out a
        second deadline on a transport already closed and say so a second time.
        """
        if self._is_closed:
            return
        failure: list[Exception] = []

        def drain() -> None:
            try:
                self._transport.flush()
            except Exception as exc:  # ruff: ignore[blind-except]
                # Unbounded code: the client library's flush, a third-party SDK with no documented exception types.
                # Nothing is swallowed: the failure crosses to the caller's thread and is raised there.
                failure.append(exc)

        flushing = threading.Thread(target=drain, name=_FLUSH_THREAD_NAME, daemon=True)
        flushing.start()
        flushing.join(timeout=FLUSH_TIMEOUT_SECONDS)
        if failure:
            raise failure[0]
        if flushing.is_alive():
            self._say_undelivered()

    @override
    def close(self) -> None:
        """Closes the transport, then prints the export failures still counted. Once: a second close does nothing.

        In that order, because the close drains the queue and a refusal met there is counted too.
        """
        if self._is_closed:
            return
        self._is_closed = True
        self._transport.close()
        self._export_path_filter.report_unreported()
        super().close()

    def _say_undelivered(self) -> None:
        """Say on stderr that the flush ran out of time, with what a fresh refresh of the credentials answers."""
        cause: str | None = None
        if self._credentials_check is not None:
            cause = _cause_from_refresh(source=self._credentials_check.source, verdict=self._credentials_check.run())
        _say_on_stderr(message=_undelivered_message(cause=cause))


class GcpLogSink(LogSink):
    """Google Cloud Logging behind one transport, a batching background thread in production.

    The transport, the project and the credentials check are resolved before the sink is built, so the
    sink itself imports nothing and a test builds it around a capture. Without a check, a flush that
    runs out of time is still said, with no cause named.

    It builds one handler. The handler's close closes the transport, whose worker thread nothing starts
    again, so a handler built on it afterwards would take every record and send none.
    """

    def __init__(self, *, transport: GcpLogTransport, project: str, credentials_check: GcpCredentialsCheck | None = None) -> None:
        super().__init__()
        self._transport = transport
        self._project = project
        self._credentials_check = credentials_check
        self._has_built_handler = False

    @override
    def make_handler(self) -> logging.Handler:
        if self._has_built_handler:
            msg = (
                "This gcp sink was installed once already, and the teardown that closed its handler closed its transport, whose "
                "worker thread nothing starts again, so it can send nothing to Cloud Logging. Build a new GcpLogSink for this install; "
                "the registered 'gcp' factory builds one at every boot."
            )
            raise RuntimeError(msg)
        handler = GcpLogHandler(transport=self._transport, project=self._project, credentials_check=self._credentials_check)
        self._has_built_handler = True
        return handler


def _credentials_source(*, config: GcpLogSinkConfig, credentials_file_path_placeholder: str | None) -> str:
    """The credentials the sink authenticates with, as a sentence names them, with the placeholder the path came from."""
    if config.credentials_file_path is None:
        return "the Application Default Credentials"
    if credentials_file_path_placeholder is not None:
        return f"the service-account key at '{config.credentials_file_path}' (resolved from '{credentials_file_path_placeholder}')"
    return f"the service-account key at '{config.credentials_file_path}'"


def _credentials_remedy(*, config: GcpLogSinkConfig, credentials_file_path_placeholder: str | None) -> str:
    """What renews the credentials, for the error that stops the boot.

    A path that came from a placeholder is fixed where the variable is set, not in the TOML, so the
    remedy says so.
    """
    if config.credentials_file_path is None:
        return (
            "Renew them (`gcloud auth application-default login` on a workstation, or the service account the machine runs as "
            "on Google Cloud), or point `credentials_file_path` in [runtime.log.gcp] at a valid service-account key"
        )
    if credentials_file_path_placeholder is not None:
        return (
            f"Point the variable that `credentials_file_path` in [runtime.log.gcp] names, '{credentials_file_path_placeholder}', "
            "at a valid service-account key where it is set"
        )
    return "Point `credentials_file_path` in [runtime.log.gcp] at a valid service-account key"


def _unloaded_credentials_message(*, source: str, remedy: str, failure: Exception) -> str:
    """What stops the boot when the credentials could not be loaded at all."""
    return (
        f"The '{LogSinkMethod.GCP}' log sink could not load {source} to write to Google Cloud Logging with "
        f"({describe_failure(failure=failure)}). {remedy}, or select the '{LogSinkMethod.JSON}' sink in [runtime.log]."
    )


def confirm_credentials_at_boot(*, credentials_check: GcpCredentialsCheck, remedy: str) -> None:
    """Refresh the credentials once before the transport starts, and stop the boot when Google refuses them.

    A refusal stops the boot because every record the sink would export is lost, and the transport
    would say so only after retrying for a minute, which a short process never reaches. A refresh that
    gets no answer says nothing about the credentials themselves, so it is said on stderr and the boot
    goes on: the transport retries, and what it cannot deliver is said by the flush at the latest.

    Raises:
        GcpLogSinkCredentialsError: If Google refuses the credentials.

    """
    verdict = credentials_check.run()
    why: str
    match verdict.outcome:
        case GcpCredentialsOutcome.REFRESHED:
            return
        case GcpCredentialsOutcome.REFUSED:
            msg = (
                f"The '{LogSinkMethod.GCP}' log sink cannot write to Google Cloud Logging: a refresh of {credentials_check.source} "
                f"was refused at boot, so every record it exported would be lost ({describe_failure(failure=verdict.failure)}). "
                f"{remedy}, or select the '{LogSinkMethod.JSON}' sink in [runtime.log]."
            )
            raise GcpLogSinkCredentialsError(msg) from verdict.failure
        case GcpCredentialsOutcome.UNREACHABLE:
            why = f"a refresh could not reach the credential endpoint ({describe_failure(failure=verdict.failure)})"
        case GcpCredentialsOutcome.UNANSWERED:
            why = f"a refresh did not answer within {CREDENTIALS_CHECK_TIMEOUT_SECONDS:g} seconds"
    _say_on_stderr(
        message=(
            f"The '{LogSinkMethod.GCP}' log sink could not confirm at boot that Google accepts {credentials_check.source}: {why}. "
            "The sink is installed and its transport retries; records it cannot deliver are said on stderr, "
            "at the latest when the process tears the sink down."
        )
    )


def make_gcp_log_sink(*, config: GcpLogSinkConfig, credentials_file_path_placeholder: str | None = None) -> GcpLogSink:
    """Build the sink that writes to Cloud Logging through the client library's background thread.

    ``config`` carries the key path already resolved; ``credentials_file_path_placeholder`` is the
    ``${…}`` spelling it was resolved from, when it was one, which the credential errors name beside
    the path so that a reader knows to fix the variable rather than the TOML.

    Where the dependency is paid for: the client library is imported here, so a process that selected
    another sink never loads it, and one that selected this sink without the extra fails here, at
    boot, with the extra and the ``json`` alternative named.

    Where the credentials are proved: a key file that cannot be read or holds no valid key, and
    Application Default Credentials that cannot be found, stop the boot before the client exists; the
    credentials the client then holds are refreshed once before the transport's thread starts, so a
    boot whose credentials Google refuses stops here naming them rather than losing every record in
    silence.

    Raises:
        MissingDependencyError: If ``google-cloud-logging`` is not installed.
        GcpLogSinkCredentialsError: If the credentials cannot be loaded, or Google refuses them.

    """
    try:
        import requests  # ruff: ignore[import-outside-top-level]
        from google.auth import exceptions as google_auth_exceptions  # ruff: ignore[import-outside-top-level]
        from google.auth.transport.requests import Request as GoogleAuthRequest  # ruff: ignore[import-outside-top-level]
        from google.cloud import logging as cloud_logging  # ruff: ignore[import-outside-top-level]
        from google.cloud.logging_v2.handlers.transports import (  # ruff: ignore[import-outside-top-level]
            BackgroundThreadTransport,
        )
        from google.oauth2 import service_account as google_service_account  # ruff: ignore[import-outside-top-level]
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

    source = _credentials_source(config=config, credentials_file_path_placeholder=credentials_file_path_placeholder)
    remedy = _credentials_remedy(config=config, credentials_file_path_placeholder=credentials_file_path_placeholder)
    client: Any
    if config.credentials_file_path is not None:
        # The key is loaded apart from the client, so that the catch covers the file and nothing else: a
        # key file that is missing or unreadable raises ``OSError``, and one that is not JSON or holds no
        # valid key raises ``ValueError``, the auth library's ``MalformedError`` among them. The client
        # raises ``OSError`` too when no project can be determined, which is not a credentials failure.
        # Handed the key, it takes the project from it when ``project_id`` is unset, as the library's own
        # ``from_service_account_json`` does.
        try:
            key_credentials = google_service_account.Credentials.from_service_account_file(  # pyright: ignore[reportUnknownMemberType]
                config.credentials_file_path
            )
        except (OSError, ValueError) as exc:
            msg = _unloaded_credentials_message(source=source, remedy=remedy, failure=exc)
            raise GcpLogSinkCredentialsError(msg) from exc
        client = cloud_logging.Client(project=config.project_id, credentials=key_credentials)
    else:
        try:
            client = cloud_logging.Client(project=config.project_id)
        except google_auth_exceptions.DefaultCredentialsError as exc:
            msg = _unloaded_credentials_message(source=source, remedy=remedy, failure=exc)
            raise GcpLogSinkCredentialsError(msg) from exc

    # The object the client authenticates every call with, after the scoping it applied: refreshing it
    # proves the credentials the transport will use, and for credentials that fetch a token, the token
    # it earns is the one the first export sends. A service-account key over gRPC signs its own token
    # instead, so there the refresh costs one exchange the transport never makes, and proves the key.
    # The library keeps the object on a private attribute, which the contract test pins.
    credentials: Any = client._credentials  # ruff: ignore[private-member-access]

    def refresh_credentials() -> None:
        # The auth library raises a 5xx or a 429 from the IAM Credentials API, from a subject-token URL or
        # from the STS exchange as a refusal that neither declares itself retryable nor carries the status,
        # so a transient outage of those endpoints would read as credentials Google refuses and stop the
        # boot. The status is read instead from a response hook on the request's own session, which keeps
        # the request the library's type: the metadata client reaches into its session. A refusal after an
        # answer that says to retry is raised again as retryable; the token endpoint's own already is.
        answered_statuses: list[int] = []

        def record_status(  # kw-only: ignore — requests calls a hook with the response positionally
            response: requests.Response, **_hook_kwargs: Any
        ) -> None:
            answered_statuses.append(response.status_code)

        session = requests.Session()
        session.hooks["response"].append(record_status)
        try:
            credentials.refresh(GoogleAuthRequest(session=session))
        except google_auth_exceptions.GoogleAuthError as exc:
            last_status = answered_statuses[-1] if answered_statuses else None
            if getattr(exc, "retryable", False) is True or last_status is None or not says_to_retry(status=last_status):
                raise
            msg = f"The credential endpoint answered {last_status}, a status that says to retry ({describe_failure(failure=exc)})"
            raise google_auth_exceptions.RefreshError(msg, retryable=True) from exc

    credentials_check = GcpCredentialsCheck(
        refresh=refresh_credentials,
        transport_error_types=(google_auth_exceptions.TransportError,),
        source=source,
    )
    confirm_credentials_at_boot(credentials_check=credentials_check, remedy=remedy)
    transport = cast("GcpLogTransport", BackgroundThreadTransport(client, config.log_name))
    return GcpLogSink(transport=transport, project=str(client.project), credentials_check=credentials_check)
