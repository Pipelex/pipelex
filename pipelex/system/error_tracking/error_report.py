"""What an error tracker receives about one error: the problem in the operator's view, the exception, and its identifiers.

An error report is built once per reported error and handed to every installed tracker (``ErrorTrackerAbstract``). It
carries the operator view of the error's problem document, the view of whoever runs the runtime, as the design rules
for the error tracker, and beside it the identifiers a tracker groups, tags and joins on, spelled with the keys a log
line about an error already carries (``pipelex.tools.log.error_fields`` and ``pipelex.errors.failure_problem``):

- **Grouping**: the problem's ``code`` and the ``raise_site``, the module and function the first exception of the
  cause chain was raised in, together the ``fingerprint``, so that one fault is one issue whatever its message says
  and whichever organization's pipe met it.
- **Tags**: the failing pipe, the run and request ids, and the classes along the cause chain.
- **Joining**: the Pipelex span the error was raised in, and OpenTelemetry's current span in the process, the host's.

**What a report must never carry is a run's content**, and what it holds is chosen for that: identifiers, the frames as
``module:line in function`` with no source line and no locals, and the problem. The problem's sentences, its parameters
and its ``diagnostics.message`` are written for an operator and may hold text taken from the caller's own submission, a
parser's finding about the caller's method or a function's own message, so a tracker sending its events off the
machine sends the identifiers and leaves those members out unless its operator chose otherwise. The live ``exception``
is handed over so a tracker can read its stack, and a tracker must never read the locals of its frames, nor attach
the request body or any input or output of the run.
"""

from enum import StrEnum
from pathlib import Path
from typing import Any

from mthds.protocol.problem.registry import CoreCode
from opentelemetry import trace
from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass

from pipelex import log
from pipelex.base_exceptions import PipelexError, iter_cause_chain
from pipelex.errors.failure_problem import ERROR_CHAIN_FIELD, failure_frames
from pipelex.errors.problem import PipelexProblem, ProblemView, make_problem
from pipelex.errors.unexpected_failure import make_unexpected_failure
from pipelex.system.telemetry.current_span import (
    PIPELEX_SPAN_ID_KEY,
    PIPELEX_TRACE_ID_KEY,
    current_span_context_for_logs,
    pipelex_span_context_for_logs,
    raising_span_context,
)
from pipelex.tools.log.error_fields import ERROR_CODE_FIELD, ERROR_TYPE_FIELD, error_fields
from pipelex.tools.log.log_context import PIPELINE_RUN_ID_FIELD, REQUEST_ID_FIELD, get_log_context

#: The key of the failing pipe's code among a report's tags, the key the log line about a run's failure gives it.
PIPE_CODE_FIELD = "pipe_code"

#: The key of the problem's domain among a report's tags: who must act on it, ``input``, ``method``, ``account``,
#: ``operator`` or ``runtime``.
ERROR_DOMAIN_FIELD = "error.domain"

#: The key of the raise site among a report's tags.
ERROR_RAISE_SITE_FIELD = "error.raise_site"

#: The key of the report's kind among its tags.
ERROR_REPORT_KIND_FIELD = "error.report_kind"


class ErrorReportKind(StrEnum):
    """How the error reached the trackers.

    - ``run_failure``: a run failed, reported by the runtime that ran it, at the run's boundary.
    - ``uncaught``: an exception reached the interpreter's exception hook, in the main thread or another one.
    - ``handled``: a host or the runtime caught the error and went on, and reports it so it is not lost.
    """

    RUN_FAILURE = "run_failure"
    UNCAUGHT = "uncaught"
    HANDLED = "handled"

    @property
    def is_handled(self) -> bool:
        """Whether something caught the error, which is every kind but ``uncaught``."""
        match self:
            case ErrorReportKind.UNCAUGHT:
                return False
            case ErrorReportKind.RUN_FAILURE | ErrorReportKind.HANDLED:
                return True


@dataclass(frozen=True, config=ConfigDict(arbitrary_types_allowed=True))
class ErrorReport:
    """One error, as every installed error tracker receives it.

    A record built and read in this process and never serialized, since it holds the live exception: a tracker turns
    it into its own event.

    Attributes:
        kind: How the error reached the trackers.
        problem: The error's problem document, in the operator's view.
        exception: The exception itself, when the error is one; ``None`` for a problem reported without one, such as
            a run whose record came out incomplete. A tracker reads its class and its stack, never its frames' locals.
        error_type: The exception's class, ``None`` without one.
        error_chain: The classes along the exception's cause chain, its own first.
        frames: The frames the failure went through down to where its first exception was raised, each
            ``module:line in function``, the innermost last.
        raise_site: Where the first exception of the cause chain was raised, as ``module:function``: no line number,
            so a release that moves the code keeps the issue.
        pipeline_run_id: The run the error belongs to, when there is one.
        request_id: The request that carried it, when there is one.
        pipe_code: The failing pipe: the pipe the problem locates, else the pipe the reporter named.
        trace_id: The trace of the Pipelex span the error was raised in, in lowercase hex.
        span_id: That span, in lowercase hex.
        host_trace_id: The trace of OpenTelemetry's current span when the error was reported, the host's own.
        host_span_id: That span.
    """

    kind: ErrorReportKind
    problem: PipelexProblem
    exception: BaseException | None = Field(default=None, repr=False)
    error_type: str | None = None
    error_chain: list[str] = Field(default_factory=list)
    frames: list[str] = Field(default_factory=list)
    raise_site: str | None = None
    pipeline_run_id: str | None = None
    request_id: str | None = None
    pipe_code: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    host_trace_id: str | None = None
    host_span_id: str | None = None

    @property
    def code(self) -> str:
        """The problem's registry code, which a tracker groups the error's issue by."""
        return self.problem.code

    @property
    def fingerprint(self) -> list[str]:
        """What tells one fault from another: the code, then the raise site when the error is an exception."""
        if self.raise_site is None:
            return [self.code]
        return [self.code, self.raise_site]

    @property
    def tags(self) -> dict[str, str]:
        """The report's scalar identifiers, under the keys a log line about an error carries, only those that are set."""
        tags: dict[str, str] = {
            ERROR_CODE_FIELD: self.code,
            ERROR_DOMAIN_FIELD: str(self.problem.domain),
            ERROR_REPORT_KIND_FIELD: self.kind,
        }
        optional_tags: dict[str, str | None] = {
            ERROR_TYPE_FIELD: self.error_type,
            ERROR_RAISE_SITE_FIELD: self.raise_site,
            PIPE_CODE_FIELD: self.pipe_code,
            PIPELINE_RUN_ID_FIELD: self.pipeline_run_id,
            REQUEST_ID_FIELD: self.request_id,
            PIPELEX_TRACE_ID_KEY: self.trace_id,
            PIPELEX_SPAN_ID_KEY: self.span_id,
        }
        tags.update({key: value for key, value in optional_tags.items() if value is not None})
        return tags

    @property
    def fields(self) -> dict[str, Any]:
        """The tags, with the cause chain's classes under ``error.chain`` when there is an exception, as the log line gives them."""
        fields: dict[str, Any] = dict(self.tags)
        if self.error_chain:
            fields[ERROR_CHAIN_FIELD] = list(self.error_chain)
        return fields


def build_operator_problem(*, exception: BaseException, pipeline_run_id: str | None, request_id: str | None) -> PipelexProblem:
    """The problem of ``exception`` in the operator's view, raising whatever building it raises.

    A Pipelex error's problem is its own. Any other exception stands as ``runtime.unexpected`` through the stand-in
    every surface gives it (``make_unexpected_failure``), whose diagnostics name its class and never hold its text,
    which can carry anything of the run's data. Most callers want ``operator_problem_of``, which never raises.
    """
    failure = exception if isinstance(exception, PipelexError) else make_unexpected_failure(error=exception)
    return failure.to_problem(view=ProblemView.OPERATOR, request_id=request_id, pipeline_run_id=pipeline_run_id)


def unexpected_operator_problem(*, pipeline_run_id: str | None, request_id: str | None) -> PipelexProblem:
    """The bare ``runtime.unexpected`` problem a failure stands as when its own problem could not be built."""
    return make_problem(code=CoreCode.RUNTIME_UNEXPECTED, view=ProblemView.OPERATOR, pipeline_run_id=pipeline_run_id, request_id=request_id)


def operator_problem_of(*, exception: BaseException, pipeline_run_id: str | None, request_id: str | None) -> PipelexProblem:
    """The problem of ``exception`` in the operator's view: a Pipelex error's own, else ``runtime.unexpected``; never raises.

    The one builder of a failure's operator problem that error reports and a failed run's webhooks share. Building a
    report must never fail in place of the error it reports, and a Pipelex error's problem reads hooks a plugin's error
    may override, so a problem that cannot be built is logged at debug level and falls back to a bare
    ``runtime.unexpected``.
    """
    try:
        return build_operator_problem(exception=exception, pipeline_run_id=pipeline_run_id, request_id=request_id)
    except Exception as problem_error:  # ruff: ignore[blind-except]
        # (2) `to_problem` runs hooks overridden across the whole error hierarchy, plugins' errors included, whose
        # exception surface cannot be enumerated; the report falls back to the catch-all code rather than failing.
        log.debug(
            "A reported error's problem could not be built",
            fields={"reported_error_type": type(exception).__name__, **error_fields(exc=problem_error)},
        )
    return unexpected_operator_problem(pipeline_run_id=pipeline_run_id, request_id=request_id)


def raise_site_of(*, exception: BaseException) -> str | None:
    """Where the first exception of ``exception``'s cause chain was raised, as ``module:function``, or ``None`` with no traceback.

    The innermost frame of the deepest exception that has a traceback: the cause of an exception was raised where that
    exception was caught, so the deepest one is where the fault began. The module is the one the frame ran in, so no
    path naming the machine's directories is written.
    """
    innermost_traceback = None
    for node in iter_cause_chain(exception):
        if node.__traceback__ is not None:
            innermost_traceback = node.__traceback__
    if innermost_traceback is None:
        return None
    while innermost_traceback.tb_next is not None:
        innermost_traceback = innermost_traceback.tb_next
    frame = innermost_traceback.tb_frame
    module = frame.f_globals.get("__name__")
    where = module if isinstance(module, str) else Path(frame.f_code.co_filename).name
    return f"{where}:{frame.f_code.co_name}"


def _raising_span_ids(*, exception: BaseException | None, problem: PipelexProblem) -> tuple[str | None, str | None]:
    """The Pipelex span an error was raised in: the deepest stamp on its cause chain, else the span held now, else the problem's."""
    span_context: trace.SpanContext | None = None
    if exception is not None:
        for node in iter_cause_chain(exception):
            span_context = raising_span_context(exception=node) or span_context
    span_context = span_context or pipelex_span_context_for_logs()
    if span_context is not None:
        return trace.format_trace_id(span_context.trace_id), trace.format_span_id(span_context.span_id)
    if problem.diagnostics is not None:
        return problem.diagnostics.trace_id, problem.diagnostics.span_id
    return None, None


def make_error_report(
    *,
    kind: ErrorReportKind,
    exception: BaseException | None = None,
    problem: PipelexProblem | None = None,
    pipeline_run_id: str | None = None,
    request_id: str | None = None,
    pipe_code: str | None = None,
) -> ErrorReport:
    """Build the report of one error, from its exception, its problem, or both.

    An identifier not given is read from the problem, then from the identifiers bound on the log context, which a run
    and a request bind for their whole duration, so a report made inside either names them as its log lines do.

    Args:
        kind: How the error reached the trackers.
        exception: The exception, when the error is one.
        problem: The problem, in the operator's view, when the reporter built it; built from ``exception`` otherwise.
        pipeline_run_id: The run the error belongs to.
        request_id: The request that carried it.
        pipe_code: The pipe the error is about, used when the problem locates no pipe.

    Returns:
        The report.

    Raises:
        ValueError: When neither an exception nor a problem is given.
    """
    log_context = get_log_context()
    bound_run_id = log_context.pipeline_run_id if log_context is not None else None
    bound_request_id = log_context.request_id if log_context is not None else None
    reported_problem: PipelexProblem
    if problem is not None:
        reported_problem = problem
    elif exception is not None:
        reported_problem = operator_problem_of(
            exception=exception,
            pipeline_run_id=pipeline_run_id or bound_run_id,
            request_id=request_id or bound_request_id,
        )
    else:
        msg = "An error report needs an exception or a problem"
        raise ValueError(msg)
    located_pipe = reported_problem.location.pipe if reported_problem.location is not None else None
    trace_id, span_id = _raising_span_ids(exception=exception, problem=reported_problem)
    host_span = current_span_context_for_logs()
    return ErrorReport(
        kind=kind,
        problem=reported_problem,
        exception=exception,
        error_type=type(exception).__name__ if exception is not None else None,
        error_chain=[type(node).__name__ for node in iter_cause_chain(exception)] if exception is not None else [],
        frames=failure_frames(error=exception) if exception is not None else [],
        raise_site=raise_site_of(exception=exception) if exception is not None else None,
        pipeline_run_id=pipeline_run_id or reported_problem.pipeline_run_id or bound_run_id,
        request_id=request_id or reported_problem.request_id or bound_request_id,
        pipe_code=located_pipe or pipe_code,
        trace_id=trace_id,
        span_id=span_id,
        host_trace_id=trace.format_trace_id(host_span.trace_id) if host_span is not None else None,
        host_span_id=trace.format_span_id(host_span.span_id) if host_span is not None else None,
    )
