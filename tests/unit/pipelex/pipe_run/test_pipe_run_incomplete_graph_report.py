from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.pipe_run import pipe_run as pipe_run_module
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.pipe_run.tracing_assembly import RunTraceEvents
from pipelex.system.data_inclusion_config import DataInclusionConfig
from pipelex.system.execution_chain import make_direct_chain
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.trace_context import TraceContext
from pipelex.test_extras.recording_error_tracker import recording_error_tracker
from tests.unit.pipelex.tracing.test_data import IncompleteGraphRun


def _router_and_job(*, mocker: MockerFixture, run_mode: PipeRunMode) -> tuple[Any, Any]:
    """A router whose run succeeds and a job tracing its graph, carrying the run's ids and its run mode."""
    job = mocker.MagicMock()
    job.pipe.code = "secret_pipe"
    job.pipe.domain_code = "secret_domain"
    job.pipe_run_params.run_mode = run_mode
    job.job_metadata = JobMetadata(
        run_metadata=RunMetadata(
            user_id="pytest",
            pipeline_run_id=IncompleteGraphRun.PIPELINE_RUN_ID,
            storage_scope="test/scope",
            read_scope=None,
            request_id=IncompleteGraphRun.REQUEST_ID,
        ),
        trace_context=TraceContext(
            graph_id=IncompleteGraphRun.PIPELINE_RUN_ID,
            data_inclusion=DataInclusionConfig(stuff_json_content=False, error_stack_traces=False, pipe_and_concept_registry=False),
            emit_graph_events=True,
            emit_usage_events=False,
            describe_pipe_io=False,
            run_mode=run_mode,
            chain=make_direct_chain(),
        ),
    )
    pipe_output = mocker.MagicMock()
    pipe_output.job_metadata = job.job_metadata
    router = mocker.AsyncMock()
    router.run = mocker.AsyncMock(return_value=pipe_output)
    return router, job


@pytest.mark.asyncio(loop_scope="class")
class TestPipeRunIncompleteGraphReport:
    async def test_a_live_run_reports_its_incomplete_graph_exactly_once(self, mocker: MockerFixture) -> None:
        router, job = _router_and_job(mocker=mocker, run_mode=PipeRunMode.LIVE)
        mocker.patch.object(
            pipe_run_module, "read_run_trace_events", return_value=RunTraceEvents(events=IncompleteGraphRun.run_with_lost_starts(), read_error=None)
        )

        with recording_error_tracker() as recorder:
            await PipeRun(pipe_router=router, reports_usage_stats=False).run(pipe_job=job)

        (report,) = recorder.reports
        assert report.code == PipelexErrorCode.RUN_GRAPH_INCOMPLETE
        assert (report.pipeline_run_id, report.request_id) == (IncompleteGraphRun.PIPELINE_RUN_ID, IncompleteGraphRun.REQUEST_ID)

    async def test_a_dry_run_reports_nothing(self, mocker: MockerFixture) -> None:
        router, job = _router_and_job(mocker=mocker, run_mode=PipeRunMode.DRY)
        mocker.patch.object(
            pipe_run_module,
            "read_run_trace_events",
            return_value=RunTraceEvents(events=IncompleteGraphRun.run_with_lost_starts(mode=PipeRunMode.DRY), read_error=None),
        )
        assemble_spy = mocker.spy(pipe_run_module, "assemble_tracing_on_output")

        with recording_error_tracker() as recorder:
            await PipeRun(pipe_router=router, reports_usage_stats=False).run(pipe_job=job)

        assert recorder.reports == []
        assert assemble_spy.call_args.kwargs["reports_incomplete_graph"] is False

    async def test_a_validation_s_run_reports_nothing(self, mocker: MockerFixture) -> None:
        """A validation runs its pipes with `reports_errors=False`; a live trace proves the policy, not the mode, decides."""
        router, job = _router_and_job(mocker=mocker, run_mode=PipeRunMode.LIVE)
        mocker.patch.object(
            pipe_run_module, "read_run_trace_events", return_value=RunTraceEvents(events=IncompleteGraphRun.run_with_lost_starts(), read_error=None)
        )

        with recording_error_tracker() as recorder:
            await PipeRun(pipe_router=router, reports_usage_stats=False, reports_errors=False).run(pipe_job=job)

        assert recorder.reports == []
