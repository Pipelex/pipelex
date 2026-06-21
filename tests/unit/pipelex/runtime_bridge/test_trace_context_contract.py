import pytest
from pytest_mock import MockerFixture

from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.graph.graph_config import DataInclusionConfig
from pipelex.graph.trace_context import TraceContext
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.runtime_bridge.bridge import PipelexPipeRunInput, run_pipe_via_bridge
from pipelex.runtime_bridge.exceptions import MissingOrchestratorError
from pipelex.runtime_bridge.execution_mode import PipelexExecutionMode


def _make_trace_context() -> TraceContext:
    data_inclusion = DataInclusionConfig(
        stuff_json_content=False,
        stuff_text_content=False,
        stuff_html_content=False,
        error_stack_traces=False,
        pipe_and_concept_registry=False,
    )
    return TraceContext(graph_id="host-graph-id", data_inclusion=data_inclusion)


def _fake_pipe_job(mocker: MockerFixture) -> PipeJob:
    fake_pipe = mocker.MagicMock()
    fake_pipe.code = "fake_pipe"
    fake_pipe.domain_code = "fake_domain"
    return PipeJob.model_construct(
        pipe=fake_pipe,
        working_memory=WorkingMemoryFactory.make_empty(),
        pipe_run_params=PipeRunParamsFactory.make_run_params(),
        job_metadata=JobMetadata(user_id="anonymous", pipeline_run_id="run-id"),
        library_crate=None,
    )


@pytest.mark.asyncio
class TestTraceContextContract:
    async def test_direct_mode_forwards_host_trace_context(self, mocker: MockerFixture) -> None:
        trace_context = _make_trace_context()
        captured: dict[str, object] = {}
        fake_job = _fake_pipe_job(mocker)

        def spy(**kwargs: object) -> PipeJob:
            captured["trace_context"] = kwargs["trace_context"]
            return fake_job

        mocker.patch("pipelex.runtime_bridge.bridge.build_pipe_job_from_input", side_effect=spy)
        mocker.patch.object(
            PipeRun,
            "run",
            new_callable=mocker.AsyncMock,
            return_value=PipeOutput(working_memory=WorkingMemoryFactory.make_empty(), pipeline_run_id="run-id"),
        )

        await run_pipe_via_bridge(
            PipelexPipeRunInput(pipe_code="fake_pipe", execution_mode=PipelexExecutionMode.DIRECT),
            trace_context=trace_context,
        )

        assert captured["trace_context"] is trace_context

    async def test_non_direct_mode_nulls_host_trace_context(self, mocker: MockerFixture) -> None:
        trace_context = _make_trace_context()
        captured: dict[str, object] = {}
        fake_job = _fake_pipe_job(mocker)

        def spy(**kwargs: object) -> PipeJob:
            captured["trace_context"] = kwargs["trace_context"]
            return fake_job

        mocker.patch("pipelex.runtime_bridge.bridge.build_pipe_job_from_input", side_effect=spy)

        # TEMPORAL_BLOCKING has no orchestrator registered in core (Temporal is now the
        # external pipelex-temporal plugin), so dispatch raises MissingOrchestratorError —
        # but only AFTER build_pipe_job_from_input runs, by which point the bridge has
        # already nulled the host trace_context for the non-DIRECT mode. This pins the
        # ``trace_context if is_direct else None`` guard against cross-graph contamination.
        with pytest.raises(MissingOrchestratorError):
            await run_pipe_via_bridge(
                PipelexPipeRunInput(pipe_code="fake_pipe", execution_mode=PipelexExecutionMode.TEMPORAL_BLOCKING),
                trace_context=trace_context,
            )

        assert captured["trace_context"] is None
