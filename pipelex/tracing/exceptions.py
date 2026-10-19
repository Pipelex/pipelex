from typing import ClassVar

from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeDeclaration


class EventLogError(PipelexError):
    """Base error for trace-event log backend failures."""

    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR


class EventLogReadError(EventLogError):
    """Raised when reading trace events from the configured backend fails.

    Backends translate their own infrastructure exceptions (e.g. botocore
    ``ClientError`` / ``BotoCoreError`` from DynamoDB on throttling, auth, or
    network failures) into this domain error at the boundary. That lets
    best-effort observability callers — graph assembly degrades to ``None``
    rather than failing the pipeline run — catch a single Pipelex error instead
    of re-widening their ``except`` clauses to raw third-party exception types.

    Its causes mix throttling and network failures, which pass, with a refused credential; the code follows
    the common case, and the cause rides the report's diagnostics.
    """

    error_code = CoreCode.RUNTIME_UNAVAILABLE


class EventLogSchemaMismatchError(EventLogReadError):
    """Raised when a trace event is well-formed JSON the current models refuse.

    The distinction that matters is against a *corrupt* line — a half-written record from a crash
    mid-write — which every backend legitimately skips with a warning, because the rest of the log is
    still the run's own record. A line that parses as JSON and is then refused by the event models is a
    different thing entirely: it was written whole, by a version whose event shape this one no longer
    accepts. Skipping those quietly is what made an old log read back as a run with no events at all,
    reported as a success, so they are counted and raised instead — a read that would return a
    truncated version of the record returns none of it, and says why.
    """

    error_code = CoreCode.RUNTIME_UNEXPECTED


class EventLogSetupError(EventLogError):
    """Raised when constructing the configured event-log backend fails.

    The sibling of :class:`EventLogReadError` for the *construction* boundary:
    backends translate the infrastructure exceptions their client setup can raise
    (e.g. botocore ``ClientError`` / ``BotoCoreError`` from ``boto3.resource`` on a
    misconfigured region or credential chain) into this domain error. Best-effort
    observability callers catch the :class:`EventLogError` base so a backend that
    cannot even be built degrades to an ``*_assembly_error`` note rather than
    aborting the pipeline run.
    """

    error_code = CoreCode.RUNTIME_MISCONFIGURED


class TraceEventModeError(PipelexError):
    """Raised when a set of trace events states no single run mode to build a graph in.

    Every trace event states the mode of the run that wrote it, `live` or `dry`, and the graph the event-replay
    assembler builds from a run's events takes that mode as its provenance. A set that mixes modes holds the events of
    more than one run, such as a dry run and a live run written under one pipeline run id, and an empty set states no
    mode at all: neither describes one run, so the assembler builds no graph from it rather than guess its mode.
    """

    error_code = CoreCode.RUNTIME_UNEXPECTED
