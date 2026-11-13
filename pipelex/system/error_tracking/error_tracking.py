"""The process's error trackers, and the one door every reported error goes through to reach them.

Boot installs the trackers ``runtime.error_tracking.trackers`` selects (``install_error_trackers``) and teardown removes
them (``reset_error_trackers``), as it installs and resets the log sink. In between, three things report to them:

- **A failed run**, which the runtime that ran it reports at the run's boundary (``PipeRun``), as ``run_failure``.
- **An uncaught exception**: while a tracker is installed, the interpreter's exception hooks, ``sys.excepthook`` and
  ``threading.excepthook``, report what reaches them as ``uncaught`` and then call the hooks that were there before.
- **Anything else a host or the runtime catches and goes on from**, through ``report_exception`` or, for a problem
  with no exception behind it, ``report_problem``, as ``handled``. A host whose runs fail outside ``PipeRun``, a
  distributed worker for instance, reports its run's failure the same way, as ``run_failure``.

**One error, one report.** An exception reported once is marked, and a later report of it, or of an error raised
``from`` it, is skipped: a run's failure reported at the run's boundary is not reported again when a host lets it reach
the interpreter's hook, nor when the host raises its own error from it.

**Reporting never fails the reporter.** With no tracker installed a report costs nothing and builds nothing. A tracker
is a plugin's code, so each call is guarded and a failing tracker is logged at debug level, the others still called.
"""

import sys
import threading
from collections.abc import Sequence
from types import TracebackType

from pipelex import log
from pipelex.base_exceptions import iter_cause_chain
from pipelex.errors.problem import PipelexProblem
from pipelex.system.error_tracking.error_report import ErrorReport, ErrorReportKind, make_error_report
from pipelex.system.error_tracking.error_tracker import ErrorTrackerAbstract
from pipelex.tools.log.error_fields import error_fields

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
        _report_uncaught(exception=exc_value)
        self._previous_excepthook(exc_type, exc_value, exc_traceback)

    def _threading_excepthook(  # kw-only: ignore — installed as threading.excepthook; called positionally
        self,
        args: threading.ExceptHookArgs,
    ) -> None:
        if args.exc_value is not None:
            _report_uncaught(exception=args.exc_value)
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


def was_reported(*, exception: BaseException) -> bool:
    """Whether ``exception``, or an error along its cause chain, was reported already."""
    return any(getattr(node, _REPORTED_STAMP, False) for node in iter_cause_chain(exception))


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
    report = make_error_report(
        kind=kind,
        exception=exception,
        problem=problem,
        pipeline_run_id=pipeline_run_id,
        request_id=request_id,
        pipe_code=pipe_code,
    )
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
    _dispatch(report=make_error_report(kind=kind, problem=problem, pipe_code=pipe_code), trackers=trackers)


def _report_uncaught(*, exception: BaseException) -> None:
    """Report an exception an interpreter hook received; an interruption or an exit is no error and is not reported."""
    if not isinstance(exception, Exception):
        return
    report_exception(exception=exception, kind=ErrorReportKind.UNCAUGHT)


def _mark_reported(*, exception: BaseException) -> None:
    try:
        setattr(exception, _REPORTED_STAMP, True)
    except (AttributeError, TypeError):
        # An exception type with `__slots__` or a read-only `__setattr__` cannot carry the mark, and may be reported twice.
        return


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
