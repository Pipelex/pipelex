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
from pipelex.plugins.orchestrator_registry import OrchestratorRegistry
from pipelex.runtime_bridge.bridge import PipelexPipeRunInput, run_pipe_via_bridge
from pipelex.runtime_bridge.delivery_mode import DeliveryMode
from pipelex.runtime_bridge.payloads import PipelexPipeRunOutput


class _FakeOrchestrator:
    supports_fire_and_forget = True

    async def run(self, *, pipe_job: PipeJob, delivery_assignment: object, delivery: DeliveryMode) -> PipelexPipeRunOutput:  # noqa: ARG002
        return PipelexPipeRunOutput(
            output_dict={},
            main_stuff_name=None,
            pipeline_run_id="run-id",
            workflow_id="fake-wf",
            is_completed=True,
            graph_spec_dump=None,
        )


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
            PipelexPipeRunInput(pipe_code="fake_pipe", orchestration_mode="direct"),
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

        # Register a stand-in orchestrator under the non-"direct" "temporal" token so dispatch
        # reaches the pipe-job build. The bridge nulls the host trace_context for any non-"direct"
        # mode, pinning the ``trace_context if is_direct else None`` guard against cross-graph
        # contamination (a distributed mode owns its own event-log infrastructure).
        registry = OrchestratorRegistry({"temporal": _FakeOrchestrator()})
        mocker.patch("pipelex.runtime_bridge.bridge.get_orchestrator_registry", return_value=registry)

        await run_pipe_via_bridge(
            PipelexPipeRunInput(pipe_code="fake_pipe", orchestration_mode="temporal"),
            trace_context=trace_context,
        )

        assert captured["trace_context"] is None
