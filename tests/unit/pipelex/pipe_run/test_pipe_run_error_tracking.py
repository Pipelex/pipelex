from contextlib import AbstractContextManager, nullcontext
from typing import Any

import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.pipe_run import pipe_run as pipe_run_module
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, WebhookTarget
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.pipeline.exceptions import PipelineInputUrlInvalidError
from pipelex.system.error_tracking.error_report import ErrorReportKind
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.test_extras.recording_error_tracker import recording_error_tracker


def _failing_job(*, mocker: MockerFixture, error: Exception | None, run_mode: PipeRunMode = PipeRunMode.LIVE) -> tuple[Any, Any]:
    """A router failing with ``error`` (or succeeding with ``None``) and a job carrying the run's ids and its run mode."""
    router = mocker.AsyncMock()
    router.run = mocker.AsyncMock(return_value=mocker.MagicMock(), side_effect=error)
    job = mocker.MagicMock()
    job.pipe.code = "two_steps"
    job.pipe_run_params.run_mode = run_mode
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

    async def test_a_dry_run_s_failure_reports_nothing(self, mocker: MockerFixture) -> None:
        """A dry run's failures are findings about the method, such as `pipelex run --dry-run` reports to whoever ran it."""
        router, job = _failing_job(mocker=mocker, error=RuntimeError("a dry run failed"), run_mode=PipeRunMode.DRY)

        with recording_error_tracker() as recorder, pytest.raises(RuntimeError):
            await PipeRun(pipe_router=router).run(pipe_job=job)

        assert recorder.reports == []

    async def test_a_caller_s_mistake_reports_nothing(self, mocker: MockerFixture) -> None:
        """A failure whose domain is the caller's, here an input of theirs, is answered to the caller and never reaches the trackers."""
        router, job = _failing_job(mocker=mocker, error=PipelineInputUrlInvalidError("not a url", input_name="document", field="document"))

        with recording_error_tracker() as recorder, pytest.raises(PipelineInputUrlInvalidError):
            await PipeRun(pipe_router=router).run(pipe_job=job)

        assert recorder.reports == []

    async def test_a_report_reuses_the_problem_built_for_the_run_s_webhooks(self, mocker: MockerFixture) -> None:
        """A run with a webhook builds its problem once; the report carries that same problem."""
        router, job = _failing_job(mocker=mocker, error=RuntimeError("router blew up"))
        executor = mocker.patch("pipelex.pipe_run.pipe_run.DeliveryExecutor").return_value
        executor.execute = mocker.AsyncMock()
        operator_problem_of = mocker.spy(pipe_run_module, "operator_problem_of")

        with recording_error_tracker() as recorder, pytest.raises(RuntimeError):
            await PipeRun(pipe_router=router).run(
                pipe_job=job, delivery_assignment=DeliveryAssignment(webhooks=[WebhookTarget(url="https://example.com/hook")])
            )

        (report,) = recorder.reports
        assert report.problem is executor.execute.call_args.kwargs["problem"]
        assert operator_problem_of.call_count == 0
        assert report.problem.diagnostics is not None
        assert report.problem.diagnostics.message == "RuntimeError"
