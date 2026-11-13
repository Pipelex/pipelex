import asyncio
from contextlib import AbstractContextManager, nullcontext
from typing import Any

import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexError
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.pipe_run import pipe_run as pipe_run_module
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, WebhookTarget
from pipelex.pipe_run.exceptions import StorageDeliveryError
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.pipeline.exceptions import PipelineInputUrlInvalidError
from pipelex.system.data_inclusion_config import DataInclusionConfig
from pipelex.system.error_tracking.error_report import ErrorReportKind
from pipelex.system.error_tracking.error_tracking import report_exception
from pipelex.system.execution_chain import make_direct_chain
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.trace_context import TraceContext
from pipelex.test_extras.recording_error_tracker import recording_error_tracker


class _EngineNotOfferedError(PipelexError):
    """The operator's 501: this deployment was given no document engine, which every run asking for one meets again."""

    error_code = PipelexErrorCode.DOCGEN_ENGINE_UNAVAILABLE


def _failing_job(*, mocker: MockerFixture, error: BaseException | None, run_mode: PipeRunMode = PipeRunMode.LIVE) -> tuple[Any, Any]:
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


def _traced(*, job: Any) -> None:
    """Give ``job`` a trace context asking for its graph, so the run's tail assembles the trace onto its output."""
    job.job_metadata = job.job_metadata.model_copy(
        update={
            "trace_context": TraceContext(
                graph_id="plr-tracked",
                data_inclusion=DataInclusionConfig(pipe_and_concept_registry=False, stuff_json_content=False, error_stack_traces=False),
                emit_graph_events=True,
                emit_usage_events=False,
                run_mode=PipeRunMode.LIVE,
                chain=make_direct_chain(),
            )
        }
    )


def _failing_tracer_close(*, mocker: MockerFixture, error: Exception) -> None:
    """A graph tracer whose closing raises ``error``."""
    tracer_manager = mocker.patch("pipelex.pipe_run.pipe_run.GraphTracerManager").get_instance.return_value
    tracer_manager.close_tracer.side_effect = error


def _failing_delivery(*, mocker: MockerFixture, error: Exception) -> None:
    """A delivery executor whose execution raises ``error``."""
    executor = mocker.patch("pipelex.pipe_run.pipe_run.DeliveryExecutor").return_value
    executor.execute = mocker.AsyncMock(side_effect=error)


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

    async def test_what_the_deployment_does_not_offer_reports_nothing(self, mocker: MockerFixture) -> None:
        """An operator's 501 is met by every run that asks for it, so, as the API server logs it at warning, no tracker receives it."""
        router, job = _failing_job(mocker=mocker, error=_EngineNotOfferedError("no document engine was given").with_params(format="pdf"))

        with recording_error_tracker() as recorder, pytest.raises(_EngineNotOfferedError):
            await PipeRun(pipe_router=router).run(pipe_job=job)

        assert recorder.reports == []

    async def test_a_delivery_that_fails_after_the_pipe_executed_is_reported_once(self, mocker: MockerFixture) -> None:
        """The run's storage failing after the pipe executed is the run's failure, reported at the run's boundary, and only there."""
        router, job = _failing_job(mocker=mocker, error=None)
        mocker.patch("pipelex.pipe_run.pipe_run.assemble_tracing_on_output")
        storage_error = StorageDeliveryError("the store is down").with_params(scheme="s3")
        executor = mocker.patch("pipelex.pipe_run.pipe_run.DeliveryExecutor").return_value
        executor.execute = mocker.AsyncMock(side_effect=storage_error)

        with recording_error_tracker() as recorder:
            with pytest.raises(StorageDeliveryError):
                await PipeRun(pipe_router=router).run(pipe_job=job, delivery_assignment=DeliveryAssignment())
            # A host answering or letting through the error it raised does not report it again.
            report_exception(exception=storage_error)

        (report,) = recorder.reports
        assert report.exception is storage_error
        assert report.kind == ErrorReportKind.RUN_FAILURE
        assert report.code == PipelexErrorCode.STORAGE_UNAVAILABLE
        assert (report.pipeline_run_id, report.request_id, report.pipe_code) == ("plr-tracked", "req-tracked", "two_steps")

    async def test_a_tracer_that_fails_to_close_after_the_pipe_executed_is_reported(self, mocker: MockerFixture) -> None:
        """The run's trace failing to close after the pipe executed is the run's failure, reported at the run's boundary."""
        router, job = _failing_job(mocker=mocker, error=None)
        mocker.patch("pipelex.pipe_run.pipe_run.assemble_tracing_on_output")
        close_error = OSError("the trace file could not be closed")
        tracer_manager = mocker.patch("pipelex.pipe_run.pipe_run.GraphTracerManager").get_instance.return_value
        tracer_manager.close_tracer.side_effect = close_error

        with recording_error_tracker() as recorder, pytest.raises(OSError, match="could not be closed"):
            await PipeRun(pipe_router=router).run(pipe_job=job)

        (report,) = recorder.reports
        assert report.exception is close_error
        assert report.kind == ErrorReportKind.RUN_FAILURE
        assert report.code == CoreCode.RUNTIME_UNEXPECTED

    async def test_a_tracer_close_s_unexpected_failure_after_the_pipe_executed_is_reported(self, mocker: MockerFixture) -> None:
        """Not only an `OSError`: whatever closing the trace raises after the pipe executed is the run's failure, and is reported."""
        router, job = _failing_job(mocker=mocker, error=None)
        mocker.patch("pipelex.pipe_run.pipe_run.assemble_tracing_on_output")
        close_error = RuntimeError("the tracer's state is broken")
        _failing_tracer_close(mocker=mocker, error=close_error)

        with recording_error_tracker() as recorder, pytest.raises(RuntimeError, match="state is broken"):
            await PipeRun(pipe_router=router).run(pipe_job=job)

        (report,) = recorder.reports
        assert report.exception is close_error
        assert report.kind == ErrorReportKind.RUN_FAILURE
        assert report.code == CoreCode.RUNTIME_UNEXPECTED
        assert (report.pipeline_run_id, report.request_id, report.pipe_code) == ("plr-tracked", "req-tracked", "two_steps")

    async def test_a_trace_that_fails_to_assemble_is_reported(self, mocker: MockerFixture) -> None:
        """Assembling the run's trace onto its output runs after the pipe executed; what it raises is the run's failure, reported."""
        router, job = _failing_job(mocker=mocker, error=None)
        _traced(job=job)
        mocker.patch("pipelex.pipe_run.pipe_run.GraphTracerManager").get_instance.return_value = None
        mocker.patch("pipelex.pipe_run.pipe_run.read_run_trace_events")
        assembly_error = KeyError("a node the graph does not hold")
        mocker.patch("pipelex.pipe_run.pipe_run.assemble_tracing_on_output", side_effect=assembly_error)

        with recording_error_tracker() as recorder, pytest.raises(KeyError):
            await PipeRun(pipe_router=router).run(pipe_job=job)

        (report,) = recorder.reports
        assert report.exception is assembly_error
        assert report.kind == ErrorReportKind.RUN_FAILURE
        assert report.code == CoreCode.RUNTIME_UNEXPECTED

    async def test_usage_statistics_that_fail_unexpectedly_are_reported(self, mocker: MockerFixture) -> None:
        """The run's statistics swallow the failures they expect; one they do not escapes the run as its failure, reported."""
        router, job = _failing_job(mocker=mocker, error=None)
        mocker.patch("pipelex.pipe_run.pipe_run.GraphTracerManager").get_instance.return_value = None
        mocker.patch("pipelex.pipe_run.pipe_run.usage_stats_are_enabled", return_value=True)
        mocker.patch("pipelex.pipe_run.pipe_run.input_kinds_of", return_value=(False, False))
        mocker.patch("pipelex.pipe_run.pipe_run.get_own_pipes", return_value=[])
        mocker.patch("pipelex.pipe_run.pipe_run.get_concept_library")
        usage_error = TypeError("an unexpected statistic")
        mocker.patch("pipelex.pipe_run.pipe_run.report_run_usage", side_effect=usage_error)

        with recording_error_tracker() as recorder, pytest.raises(TypeError, match="unexpected statistic"):
            await PipeRun(pipe_router=router).run(pipe_job=job)

        (report,) = recorder.reports
        assert report.exception is usage_error
        assert report.kind == ErrorReportKind.RUN_FAILURE

    async def test_a_delivery_s_unexpected_failure_is_reported(self, mocker: MockerFixture) -> None:
        """Not only a `DeliveryError`: whatever the delivery raises after the pipe executed is the run's failure, and is reported."""
        router, job = _failing_job(mocker=mocker, error=None)
        mocker.patch("pipelex.pipe_run.pipe_run.assemble_tracing_on_output")
        delivery_error = RuntimeError("the delivery's own bug")
        _failing_delivery(mocker=mocker, error=delivery_error)

        with recording_error_tracker() as recorder, pytest.raises(RuntimeError, match="delivery's own bug"):
            await PipeRun(pipe_router=router).run(pipe_job=job, delivery_assignment=DeliveryAssignment())

        (report,) = recorder.reports
        assert report.exception is delivery_error
        assert report.kind == ErrorReportKind.RUN_FAILURE

    @pytest.mark.parametrize("fails_delivery", [False, True])
    async def test_a_cancelled_run_whose_tail_fails_stays_cancelled_and_reports_nothing(self, mocker: MockerFixture, fails_delivery: bool) -> None:
        """A cancelled run whose trace will not close, or whose delivery fails too, still propagates its cancellation, and no tracker hears of it."""
        router, job = _failing_job(mocker=mocker, error=asyncio.CancelledError())
        _failing_tracer_close(mocker=mocker, error=OSError("the trace file could not be closed"))
        delivery_assignment: DeliveryAssignment | None = None
        if fails_delivery:
            _failing_delivery(mocker=mocker, error=StorageDeliveryError("the store is down").with_params(scheme="s3"))
            delivery_assignment = DeliveryAssignment()

        with recording_error_tracker() as recorder, pytest.raises(asyncio.CancelledError):
            await PipeRun(pipe_router=router).run(pipe_job=job, delivery_assignment=delivery_assignment)

        assert recorder.reports == []

    @pytest.mark.parametrize("failing_stage", ["tracer_close", "delivery"])
    async def test_a_failed_pipe_whose_tail_also_raises_reports_once_the_exception_the_caller_receives(
        self, mocker: MockerFixture, failing_stage: str
    ) -> None:
        """The tail's exception replaces the pipe's own on its way to the caller; that one is reported, and the pipe's is not reported beside it."""
        router_error = RuntimeError("router blew up")
        router, job = _failing_job(mocker=mocker, error=router_error)
        tail_error = RuntimeError("the tail's own bug")
        delivery_assignment: DeliveryAssignment | None = None
        if failing_stage == "tracer_close":
            _failing_tracer_close(mocker=mocker, error=tail_error)
        else:
            mocker.patch("pipelex.pipe_run.pipe_run.GraphTracerManager").get_instance.return_value = None
            _failing_delivery(mocker=mocker, error=tail_error)
            delivery_assignment = DeliveryAssignment()

        with recording_error_tracker() as recorder, pytest.raises(RuntimeError, match="tail's own bug") as raised:
            await PipeRun(pipe_router=router).run(pipe_job=job, delivery_assignment=delivery_assignment)

        assert raised.value is tail_error
        (report,) = recorder.reports
        assert report.exception is tail_error
        assert report.kind == ErrorReportKind.RUN_FAILURE
