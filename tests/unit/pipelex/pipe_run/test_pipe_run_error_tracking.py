from contextlib import AbstractContextManager, nullcontext
from typing import Any

import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.system.error_tracking.error_report import ErrorReportKind
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.test_extras.recording_error_tracker import recording_error_tracker


def _failing_job(*, mocker: MockerFixture, error: Exception | None) -> tuple[Any, Any]:
    """A router failing with ``error`` (or succeeding with ``None``) and a job carrying the run's ids."""
    router = mocker.AsyncMock()
    router.run = mocker.AsyncMock(return_value=mocker.MagicMock(), side_effect=error)
    job = mocker.MagicMock()
    job.pipe.code = "two_steps"
    job.job_metadata = JobMetadata(
        run_metadata=RunMetadata(
            user_id="pytest", pipeline_run_id="plr-tracked", storage_scope="test/scope", read_scope=None, request_id="req-tracked"
        )
    )
    return router, job


@pytest.mark.asyncio(loop_scope="class")
class TestPipeRunErrorTracking:
    async def test_a_failed_run_reaches_the_error_trackers_with_its_ids_and_its_pipe(self, mocker: MockerFixture) -> None:
        router_error = RuntimeError("router blew up")
        router, job = _failing_job(mocker=mocker, error=router_error)

        with recording_error_tracker() as recorder, pytest.raises(RuntimeError, match="router blew up"):
            await PipeRun(pipe_router=router).run(pipe_job=job)

        assert len(recorder.reports) == 1
        report = recorder.reports[0]
        assert report.exception is router_error
        assert report.kind == ErrorReportKind.RUN_FAILURE
        assert report.code == CoreCode.RUNTIME_UNEXPECTED
        assert (report.pipeline_run_id, report.request_id, report.pipe_code) == ("plr-tracked", "req-tracked", "two_steps")
        assert report.problem.diagnostics is not None

    @pytest.mark.parametrize(
        ("router_error", "reports_errors"),
        [
            (None, True),
            (RuntimeError("a validation's dry run failed"), False),
        ],
    )
    async def test_a_run_that_succeeds_or_a_validation_run_reports_nothing(
        self, mocker: MockerFixture, router_error: Exception | None, reports_errors: bool
    ) -> None:
        router, job = _failing_job(mocker=mocker, error=router_error)
        mocker.patch("pipelex.pipe_run.pipe_run.assemble_tracing_on_output")

        expectation: AbstractContextManager[Any] = pytest.raises(RuntimeError) if router_error is not None else nullcontext()

        with recording_error_tracker() as recorder, expectation:
            await PipeRun(pipe_router=router, reports_errors=reports_errors).run(pipe_job=job)

        assert recorder.reports == []
