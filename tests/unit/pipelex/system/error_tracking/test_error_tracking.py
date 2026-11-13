import sys
import threading
from collections.abc import Generator

import pytest
from mthds.protocol.problem.registry import CoreCode
from opentelemetry.sdk.trace import Span as SdkSpan
from opentelemetry.sdk.trace import TracerProvider
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex.errors.problem import ProblemView, make_problem
from pipelex.system.error_tracking.error_report import ErrorReport, ErrorReportKind
from pipelex.system.error_tracking.error_tracker import ErrorTrackerAbstract
from pipelex.system.error_tracking.error_tracking import (
    has_error_trackers,
    install_error_trackers,
    installed_error_trackers,
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
