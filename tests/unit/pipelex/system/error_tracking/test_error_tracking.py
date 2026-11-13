import sys
import threading
from collections.abc import Generator
from typing import Any

import pytest
from mthds.protocol.problem.registry import CoreCode, ProblemDomain
from opentelemetry.sdk.trace import Span as SdkSpan
from opentelemetry.sdk.trace import TracerProvider
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex.errors.problem import ProblemView, make_problem
from pipelex.system.error_tracking import error_tracking as error_tracking_module
from pipelex.system.error_tracking.error_report import ErrorReport, ErrorReportKind
from pipelex.system.error_tracking.error_tracker import ErrorTrackerAbstract
from pipelex.system.error_tracking.error_tracking import (
    has_error_trackers,
    install_error_trackers,
    installed_error_trackers,
    reaches_error_trackers,
    report_exception,
    report_problem,
    reset_error_trackers,
    was_reported,
)
from pipelex.system.telemetry.current_span import pipelex_span_active
from pipelex.test_extras.recording_error_tracker import RecordingErrorTracker, recording_error_tracker
from pipelex.tools.log.log_context import bind_log_context


class _FailingErrorTracker(ErrorTrackerAbstract):
    @override
    def report(self, *, report: ErrorReport) -> None:
        msg = "the tracker's SDK is down"
        raise RuntimeError(msg)

    @override
    def close(self) -> None:
        msg = "the tracker could not flush"
        raise RuntimeError(msg)


@pytest.fixture(autouse=True)
def keep_the_installed_trackers() -> Generator[None, None, None]:
    """Each test installs its own trackers; the ones the session's boot installed come back after it."""
    previous_trackers = installed_error_trackers()
    previous_excepthook = sys.excepthook
    previous_threading_excepthook = threading.excepthook
    yield
    install_error_trackers(trackers=previous_trackers)
    sys.excepthook = previous_excepthook
    threading.excepthook = previous_threading_excepthook


class _UnprintableError(Exception):
    """An exception whose ``__str__`` raises, as a buggy class of a dependency's can."""

    @override
    def __str__(self) -> str:
        msg = "this error cannot be printed"
        raise RuntimeError(msg)


# The prefix of the attributes the runtime marks an exception with: reported once, and the Pipelex span it left.
_PIPELEX_MARK_PREFIX = "__pipelex_"


class _UnreadableMarkError(Exception):
    """An exception whose class's ``__getattribute__`` raises when the runtime's marks are read."""

    @override
    def __getattribute__(self, name: str) -> Any:
        if name.startswith(_PIPELEX_MARK_PREFIX):
            msg = "this error's attributes cannot be read"
            raise RuntimeError(msg)
        return super().__getattribute__(name)


class _UnwalkableError(Exception):
    """An exception whose class's ``__getattribute__`` raises when its cause is read."""

    @override
    def __getattribute__(self, name: str) -> Any:
        if name == "__cause__":
            msg = "this error's cause cannot be read"
            raise RuntimeError(msg)
        return super().__getattribute__(name)


class _UnmarkableError(Exception):
    """An exception whose class's ``__setattr__`` raises, other than an AttributeError or a TypeError, when the runtime marks it."""

    @override
    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith(_PIPELEX_MARK_PREFIX):
            msg = "this error's attributes cannot be set"
            raise RuntimeError(msg)
        super().__setattr__(name, value)


def _raised(*, error: Exception) -> Exception:
    """``error`` as it is once raised and caught, carrying its traceback."""
    try:
        raise error
    except Exception as exc:
        return exc


class TestErrorTracking:
    def test_a_report_reaches_every_tracker_in_order(self) -> None:
        first = RecordingErrorTracker()
        second = RecordingErrorTracker()
        install_error_trackers(trackers=[first, second])
        error = _raised(error=ValueError("boom"))

        report_exception(exception=error)

        assert [report.exception for report in first.reports] == [error]
        assert [report.exception for report in second.reports] == [error]
        assert first.reports[0].kind == ErrorReportKind.HANDLED
        assert first.reports[0].code == CoreCode.RUNTIME_UNEXPECTED

    def test_an_error_is_reported_once_even_when_a_host_raises_its_own_from_it(self) -> None:
        with recording_error_tracker() as recorder:
            run_error = _raised(error=ValueError("the run failed"))
            report_exception(exception=run_error, kind=ErrorReportKind.RUN_FAILURE)
            host_error = RuntimeError("the host gave up")
            host_error.__cause__ = run_error

            report_exception(exception=run_error)
            report_exception(exception=host_error, kind=ErrorReportKind.UNCAUGHT)

        assert [report.kind for report in recorder.reports] == [ErrorReportKind.RUN_FAILURE]
        assert was_reported(exception=host_error)

    def test_a_failing_tracker_never_fails_the_reporter_and_the_others_still_receive_the_error(self) -> None:
        recorder = RecordingErrorTracker()
        install_error_trackers(trackers=[_FailingErrorTracker(), recorder])

        report_exception(exception=_raised(error=ValueError("boom")))

        assert len(recorder.reports) == 1

    def test_with_no_tracker_nothing_is_built(self, mocker: MockerFixture) -> None:
        install_error_trackers(trackers=[])
        make_report = mocker.patch("pipelex.system.error_tracking.error_tracking.make_error_report")
        error = ValueError("boom")

        report_exception(exception=error)

        make_report.assert_not_called()
        assert not has_error_trackers()
        assert not was_reported(exception=error)

    def test_the_ids_bound_on_the_log_context_reach_a_report_that_was_not_given_them(self) -> None:
        with recording_error_tracker() as recorder, bind_log_context(request_id="req-42", pipeline_run_id="plr-42"):
            report_exception(exception=_raised(error=ValueError("boom")))

        report = recorder.reports[0]
        assert (report.request_id, report.pipeline_run_id) == ("req-42", "plr-42")
        assert (report.problem.request_id, report.problem.pipeline_run_id) == ("req-42", "plr-42")

    def test_the_report_names_the_pipelex_span_the_error_was_raised_in_after_the_span_closed(self) -> None:
        span = TracerProvider().get_tracer(__name__).start_span("pipe")
        assert isinstance(span, SdkSpan)
        error: Exception | None = None
        try:
            with pipelex_span_active(span=span):
                msg = "boom"
                raise ValueError(msg)
        except ValueError as exc:
            error = exc
        assert error is not None

        with recording_error_tracker() as recorder:
            report_exception(exception=error)

        assert recorder.reports[0].span_id == f"{span.get_span_context().span_id:016x}"
        assert recorder.reports[0].trace_id == f"{span.get_span_context().trace_id:032x}"

    def test_a_problem_with_no_exception_is_reported_under_its_code(self) -> None:
        problem = make_problem(code=CoreCode.RUNTIME_UNEXPECTED, view=ProblemView.OPERATOR, pipeline_run_id="plr-7", request_id="req-7")

        with recording_error_tracker() as recorder:
            report_problem(problem=problem)

        report = recorder.reports[0]
        assert report.exception is None
        assert report.fingerprint == [CoreCode.RUNTIME_UNEXPECTED]
        assert (report.pipeline_run_id, report.request_id) == ("plr-7", "req-7")
        assert report.kind.is_handled

    def test_the_interpreter_hooks_report_an_uncaught_exception_and_hand_it_on(self, mocker: MockerFixture) -> None:
        previous_hook = mocker.MagicMock()
        sys.excepthook = previous_hook
        recorder = RecordingErrorTracker()
        install_error_trackers(trackers=[recorder])
        error = _raised(error=ValueError("boom"))

        sys.excepthook(ValueError, error, error.__traceback__)

        assert [report.kind for report in recorder.reports] == [ErrorReportKind.UNCAUGHT]
        assert not recorder.reports[0].kind.is_handled
        previous_hook.assert_called_once_with(ValueError, error, error.__traceback__)

    def test_an_interruption_is_handed_on_without_being_reported(self, mocker: MockerFixture) -> None:
        previous_hook = mocker.MagicMock()
        sys.excepthook = previous_hook
        recorder = RecordingErrorTracker()
        install_error_trackers(trackers=[recorder])
        interruption = KeyboardInterrupt()

        sys.excepthook(KeyboardInterrupt, interruption, None)

        assert recorder.reports == []
        previous_hook.assert_called_once()

    def test_a_thread_that_dies_reports_its_exception(self, mocker: MockerFixture) -> None:
        threading.excepthook = mocker.MagicMock()
        recorder = RecordingErrorTracker()
        install_error_trackers(trackers=[recorder])

        def _fail() -> None:
            msg = "boom in a thread"
            raise ValueError(msg)

        worker = threading.Thread(target=_fail)
        worker.start()
        worker.join()

        assert [report.error_type for report in recorder.reports] == ["ValueError"]

    def test_reset_closes_every_tracker_and_puts_the_hooks_back(self) -> None:
        previous_excepthook = sys.excepthook
        recorder = RecordingErrorTracker()
        install_error_trackers(trackers=[_FailingErrorTracker(), recorder])
        assert sys.excepthook != previous_excepthook

        reset_error_trackers()

        assert recorder.is_closed
        assert installed_error_trackers() == ()
        assert sys.excepthook == previous_excepthook

    def test_installing_no_tracker_installs_no_hook(self) -> None:
        previous_excepthook = sys.excepthook

        install_error_trackers(trackers=[])

        assert sys.excepthook == previous_excepthook

    def test_an_exception_whose_str_raises_never_fails_the_reporter(self) -> None:
        with recording_error_tracker() as recorder:
            report_exception(exception=_raised(error=_UnprintableError()))

        assert [report.error_type for report in recorder.reports] == ["_UnprintableError"]

    def test_a_report_that_cannot_be_built_is_dropped_and_never_raises(self, mocker: MockerFixture) -> None:
        mocker.patch.object(error_tracking_module, "make_error_report", side_effect=RuntimeError("the report could not be built"))
        error = _raised(error=_UnprintableError())

        with recording_error_tracker() as recorder:
            report_exception(exception=error)
            report_problem(problem=make_problem(code=CoreCode.RUNTIME_UNEXPECTED, view=ProblemView.OPERATOR))

        assert recorder.reports == []
        # Not marked: nothing was reported, so a later report of it may still go out.
        assert not was_reported(exception=error)

    def test_the_previous_hook_is_called_even_when_reporting_fails(self, mocker: MockerFixture) -> None:
        previous_hook = mocker.MagicMock()
        sys.excepthook = previous_hook
        previous_threading_hook = mocker.MagicMock()
        threading.excepthook = previous_threading_hook
        install_error_trackers(trackers=[RecordingErrorTracker()])
        mocker.patch.object(error_tracking_module, "_report_uncaught", side_effect=RuntimeError("reporting failed"))
        error = _raised(error=ValueError("uncaught"))

        with pytest.raises(RuntimeError, match="reporting failed"):
            sys.excepthook(ValueError, error, error.__traceback__)
        thread_args = mocker.MagicMock(exc_value=error)
        with pytest.raises(RuntimeError, match="reporting failed"):
            threading.excepthook(thread_args)

        previous_hook.assert_called_once_with(ValueError, error, error.__traceback__)
        previous_threading_hook.assert_called_once_with(thread_args)

    @pytest.mark.parametrize(
        ("status", "domain", "reaches"),
        [
            (500, ProblemDomain.RUNTIME, True),
            (500, ProblemDomain.OPERATOR, True),
            (503, ProblemDomain.RUNTIME, True),
            # What this deployment does not offer, which a caller meets each time it asks: nothing is broken.
            (501, ProblemDomain.OPERATOR, False),
            (501, ProblemDomain.RUNTIME, False),
            # A caller's mistake or a refusal the caller can avoid.
            (422, ProblemDomain.INPUT, False),
            (502, ProblemDomain.INPUT, False),
            (500, ProblemDomain.METHOD, False),
            (500, ProblemDomain.ACCOUNT, False),
            # A 4xx is the caller's to act on, whatever its domain, such as a provider's rate limit passed through.
            (429, ProblemDomain.RUNTIME, False),
            (409, ProblemDomain.OPERATOR, False),
        ],
    )
    def test_only_a_fault_the_server_must_fix_reaches_the_trackers(self, status: int, domain: ProblemDomain, reaches: bool) -> None:
        assert reaches_error_trackers(status=status, domain=domain) is reaches

    @pytest.mark.parametrize(
        ("error_class", "report_count"),
        [
            (_UnreadableMarkError, 1),
            (_UnmarkableError, 1),
            # Its report cannot be built either, since the report walks the cause chain too, so it is dropped.
            (_UnwalkableError, 0),
        ],
    )
    def test_an_exception_whose_class_refuses_the_mark_never_fails_the_reporter(self, error_class: type[Exception], report_count: int) -> None:
        """Reading or writing the reported mark runs the exception class's own code, whatever it raises the error stands."""
        error = _raised(error=error_class("boom"))

        with recording_error_tracker() as recorder:
            report_exception(exception=error)

        assert [report.error_type for report in recorder.reports] == [error_class.__name__] * report_count
        # Unreadable or unmarked, it counts as not reported: it may be reported twice, never fail the reporter.
        assert was_reported(exception=error) is False
