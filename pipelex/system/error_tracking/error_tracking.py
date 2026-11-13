"""The process's error trackers, and the one door every reported error goes through to reach them.

Boot installs the trackers ``runtime.error_tracking.trackers`` selects (``install_error_trackers``) and teardown removes
them (``reset_error_trackers``), as it installs and resets the log sink. In between, three things report to them:

- **A failed run**, which the runtime that ran it reports at the run's boundary (``PipeRun``), as ``run_failure``,
  when the failure is the operator's to fix (``reaches_error_trackers``) and the run is no dry run. What is reported
  is the exception that escapes the run, the pipe's own or one the run's tail raised after the pipe executed, such as
  its trace, its statistics or its delivery failing, once per run; a cancelled run reports nothing.
- **An uncaught exception**: while a tracker is installed, the interpreter's exception hooks, ``sys.excepthook`` and
  ``threading.excepthook``, report what reaches them as ``uncaught`` and then call the hooks that were there before.
- **Anything else a host or the runtime catches and goes on from**, through ``report_exception`` or, for a problem
  with no exception behind it, ``report_problem``, as ``handled``. A host whose runs fail outside ``PipeRun``, a
  distributed worker for instance, reports its run's failure the same way, as ``run_failure``.

**One error, one report.** An exception reported once is marked, and a later report of it, or of an error raised
``from`` it, is skipped: a run's failure reported at the run's boundary is not reported again when a host lets it reach
the interpreter's hook, nor when the host raises its own error from it.

**Reporting never fails the reporter.** With no tracker installed a report costs nothing and builds nothing. A report
that cannot be built, an exception whose ``__str__`` raises for instance, is logged at debug level and dropped, and the
interpreter's previous hooks are still called. A tracker is a plugin's code, so each call is guarded and a failing
tracker is logged at debug level, the others still called.
"""

import sys
import threading
from collections.abc import Sequence
from http import HTTPStatus
from types import TracebackType

from mthds.protocol.problem.registry import ProblemDomain

from pipelex import log
from pipelex.base_exceptions import iter_cause_chain
from pipelex.errors.problem import PipelexProblem
from pipelex.system.error_tracking.error_report import ErrorReport, ErrorReportKind, make_error_report
from pipelex.system.error_tracking.error_tracker import ErrorTrackerAbstract
from pipelex.tools.log.error_fields import ERROR_TYPE_FIELD, error_fields

# The attribute an exception carries once it was reported, so that it is reported once.
_REPORTED_STAMP = "__pipelex_error_reported__"

# The field a debug line about a failing tracker names the code of the error it could not report under.
_REPORTED_ERROR_CODE_FIELD = "reported_error_code"


class _UncaughtExceptionHooks:
    """The interpreter hooks that report an uncaught exception, chained in front of the ones they replace."""

    def __init__(self) -> None:
        self._previous_excepthook = sys.excepthook
        self._previous_threading_excepthook = threading.excepthook
        sys.excepthook = self._excepthook
        threading.excepthook = self._threading_excepthook

    def restore(self) -> None:
        """Put back the hooks these replaced, unless something replaced these in turn, whose hook is then left in place."""
        if sys.excepthook == self._excepthook:
            sys.excepthook = self._previous_excepthook
        if threading.excepthook == self._threading_excepthook:
            threading.excepthook = self._previous_threading_excepthook

    def _excepthook(  # kw-only: ignore — installed as sys.excepthook; the interpreter calls it positionally
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> None:
        try:
            _report_uncaught(exception=exc_value)
        finally:
            self._previous_excepthook(exc_type, exc_value, exc_traceback)

    def _threading_excepthook(  # kw-only: ignore — installed as threading.excepthook; called positionally
        self,
        args: threading.ExceptHookArgs,
    ) -> None:
        try:
            if args.exc_value is not None:
                _report_uncaught(exception=args.exc_value)
        finally:
            self._previous_threading_excepthook(args)


class _ErrorTrackingState:
    """The installed trackers and the hooks installed with them; one per process, guarded by its lock."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.trackers: tuple[ErrorTrackerAbstract, ...] = ()
        self.hooks: _UncaughtExceptionHooks | None = None


_STATE = _ErrorTrackingState()


def install_error_trackers(*, trackers: Sequence[ErrorTrackerAbstract]) -> None:
    """Make ``trackers`` the process's error trackers, and report uncaught exceptions to them while there is one.

    Replaces the trackers installed before without closing them, so a caller that swaps trackers for a while, a test
    for instance, can put the previous ones back; ``reset_error_trackers`` is what closes the installed ones. Called by
    boot with the trackers the configuration selects; a host that boots no Pipelex runtime may call it too.
    """
    with _STATE.lock:
        if _STATE.hooks is not None:
            _STATE.hooks.restore()
        _STATE.trackers = tuple(trackers)
        _STATE.hooks = _UncaughtExceptionHooks() if _STATE.trackers else None


def reset_error_trackers() -> None:
    """Remove the installed trackers, closing each, and put back the interpreter hooks; never raises."""
    with _STATE.lock:
        trackers = _STATE.trackers
        hooks = _STATE.hooks
        _STATE.trackers = ()
        _STATE.hooks = None
    if hooks is not None:
        hooks.restore()
    for tracker in trackers:
        try:
            tracker.close()
        except Exception as close_error:  # ruff: ignore[blind-except]
            # (2) a tracker is a plugin's code whose exception surface cannot be enumerated, and the others still close.
            log.debug("An error tracker could not be closed", fields={"error_tracker": type(tracker).__name__, **error_fields(exc=close_error)})


def installed_error_trackers() -> tuple[ErrorTrackerAbstract, ...]:
    """The trackers installed now, in the order a report reaches them."""
    return _STATE.trackers


def has_error_trackers() -> bool:
    """Whether a tracker is installed, so a reporter can skip building what only a report needs."""
    return bool(_STATE.trackers)


def reaches_error_trackers(*, status: int, domain: ProblemDomain) -> bool:
    """Whether a failure is the operator's to fix, and so is reported to the error trackers, from its status and its domain.

    The one rule every surface reports a failure by: a failed run (``PipeRun``), weighed by its problem's status
    (``problem_status_of``), and an error the API server answers, weighed by the status it answers with, whose record
    logs at ``error`` exactly when this holds. A failure reaches the trackers only when the server has something to fix:

    - a 4xx is the caller's to act on, a mistake or a benign conflict, and is not reported;
    - a ``501`` states that this deployment does not offer what was asked, custom code without a sandbox or a document
      engine it was not given. The operator decides whether to offer it, but nothing is broken, and the caller meets
      the refusal each time it asks again, so it is not reported, or any caller could flood the trackers by repeating it;
    - any other 5xx is reported when its domain is the runtime's or the operator's, and not when it is the caller's,
      ``input``, ``method`` or ``account``, a refusal the caller can avoid.

    Every report carries its domain as the ``error.domain`` tag, so reporting the caller's failures too would change
    this predicate alone.

    Args:
        status: The HTTP status the failure is, or would be, answered with.
        domain: Who must act on it, its problem's domain.
    """
    match status:
        case HTTPStatus.NOT_IMPLEMENTED:
            return False
        case server_status if server_status >= HTTPStatus.INTERNAL_SERVER_ERROR:
            match domain:
                case ProblemDomain.OPERATOR | ProblemDomain.RUNTIME:
                    return True
                case ProblemDomain.INPUT | ProblemDomain.METHOD | ProblemDomain.ACCOUNT:
                    return False
        case _:
            return False


def was_reported(*, exception: BaseException) -> bool:
    """Whether ``exception``, or an error along its cause chain, was reported already; never raises.

    The walk reads attributes of each exception, its ``__cause__`` and the mark, which run its class's own
    ``__getattribute__``. An exception that refuses to be read this way counts as not reported: it may then be reported
    twice, but never fails the reporter in place of the error it reports.
    """
    try:
        return any(getattr(node, _REPORTED_STAMP, False) for node in iter_cause_chain(exception))
    except Exception as read_error:  # ruff: ignore[blind-except]
        # (2) reading an exception's attributes runs its class's own `__getattribute__`, and testing the mark runs the
        # mark's `__bool__`, whose exception surface cannot be enumerated; reporting must never replace the error.
        log.debug(
            "Whether an error was reported already could not be read",
            fields={"reported_error_type": type(exception).__name__, ERROR_TYPE_FIELD: type(read_error).__name__},
        )
        return False


def report_exception(
    *,
    exception: BaseException,
    kind: ErrorReportKind = ErrorReportKind.HANDLED,
    problem: PipelexProblem | None = None,
    pipeline_run_id: str | None = None,
    request_id: str | None = None,
    pipe_code: str | None = None,
) -> None:
    """Report ``exception`` to every installed tracker, once.

    Args:
        exception: The error.
        kind: How it reached the trackers: ``handled`` by default, ``run_failure`` for a run's failure.
        problem: Its problem in the operator's view, when the reporter built it already; built here otherwise.
        pipeline_run_id: The run it belongs to; read from the bound log context when not given.
        request_id: The request that carried it; read from the bound log context when not given.
        pipe_code: The pipe it is about, used when its problem locates none.
    """
    trackers = _STATE.trackers
    if not trackers or was_reported(exception=exception):
        return
    try:
        report = make_error_report(
            kind=kind,
            exception=exception,
            problem=problem,
            pipeline_run_id=pipeline_run_id,
            request_id=request_id,
            pipe_code=pipe_code,
        )
    except Exception as build_error:  # ruff: ignore[blind-except]
        # (2) building a report reads the exception itself, its class's `__str__` or `__repr__` included, whose
        # exception surface cannot be enumerated; a report that cannot be built must never replace the error.
        log.debug("An error report could not be built", fields={"reported_error_type": type(exception).__name__, **error_fields(exc=build_error)})
        return
    _mark_reported(exception=exception)
    _dispatch(report=report, trackers=trackers)


def report_problem(
    *,
    problem: PipelexProblem,
    kind: ErrorReportKind = ErrorReportKind.HANDLED,
    pipe_code: str | None = None,
) -> None:
    """Report a problem that no exception stands behind, such as a run whose record came out incomplete.

    The report groups by the problem's code alone, having no raise site, so the code is one the reporter keeps stable.

    Args:
        problem: The problem, in the operator's view, carrying its run and request ids when it has them.
        kind: How it reached the trackers, ``handled`` by default.
        pipe_code: The pipe it is about, used when the problem locates none.
    """
    trackers = _STATE.trackers
    if not trackers:
        return
    try:
        report = make_error_report(kind=kind, problem=problem, pipe_code=pipe_code)
    except Exception as build_error:  # ruff: ignore[blind-except]
        # (2) building a report reads the problem and the bound log and span contexts; whatever it raises, reporting
        # must never fail the reporter.
        log.debug("An error report could not be built", fields={_REPORTED_ERROR_CODE_FIELD: problem.code, **error_fields(exc=build_error)})
        return
    _dispatch(report=report, trackers=trackers)


def _report_uncaught(*, exception: BaseException) -> None:
    """Report an exception an interpreter hook received; an interruption or an exit is no error and is not reported."""
    if not isinstance(exception, Exception):
        return
    report_exception(exception=exception, kind=ErrorReportKind.UNCAUGHT)


def _mark_reported(*, exception: BaseException) -> None:
    """Mark ``exception`` as reported, when its class lets it carry the mark; never raises."""
    try:
        setattr(exception, _REPORTED_STAMP, True)
    except Exception as mark_error:  # ruff: ignore[blind-except]
        # (2) setting an attribute runs the exception class's own `__setattr__`, whose exception surface cannot be
        # enumerated: `__slots__` refuse it with an AttributeError, a read-only class with a TypeError, and a class of
        # its own with anything. The exception then goes unmarked and may be reported twice, but the error stands.
        log.debug(
            "A reported error could not be marked as reported",
            fields={"reported_error_type": type(exception).__name__, ERROR_TYPE_FIELD: type(mark_error).__name__},
        )


def _dispatch(*, report: ErrorReport, trackers: tuple[ErrorTrackerAbstract, ...]) -> None:
    for tracker in trackers:
        try:
            tracker.report(report=report)
        except Exception as tracker_error:  # ruff: ignore[blind-except]
            # (2) a tracker is a plugin's code whose exception surface cannot be enumerated; a failure to report must
            # never replace the error being reported, and the other trackers still receive it.
            log.debug(
                "An error tracker could not report an error",
                fields={"error_tracker": type(tracker).__name__, _REPORTED_ERROR_CODE_FIELD: report.code, **error_fields(exc=tracker_error)},
            )
