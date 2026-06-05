import pytest
from pytest_mock import MockerFixture

from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.graph.graph_config import DataInclusionConfig
from pipelex.graph.graph_context import GraphContext
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.runtime_bridge.bridge import PipelexPipeRunInput, run_pipe_via_bridge
from pipelex.runtime_bridge.execution_mode import PipelexExecutionMode


def _make_graph_context() -> GraphContext:
    data_inclusion = DataInclusionConfig(
        stuff_json_content=False,
        stuff_text_content=False,
        stuff_html_content=False,
        error_stack_traces=False,
        pipe_and_concept_registry=False,
    )
    return GraphContext(graph_id="host-graph-id", data_inclusion=data_inclusion)


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
class TestGraphContextContract:
    async def test_direct_mode_forwards_host_graph_context(self, mocker: MockerFixture) -> None:
        graph_context = _make_graph_context()
        captured: dict[str, object] = {}
        fake_job = _fake_pipe_job(mocker)

        def spy(**kwargs: object) -> PipeJob:
            captured["graph_context"] = kwargs["graph_context"]
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
            graph_context=graph_context,
        )

        assert captured["graph_context"] is graph_context

    async def test_temporal_mode_nulls_host_graph_context(self, mocker: MockerFixture) -> None:
        graph_context = _make_graph_context()
        captured: dict[str, object] = {}
        fake_job = _fake_pipe_job(mocker)

        def spy(**kwargs: object) -> PipeJob:
            captured["graph_context"] = kwargs["graph_context"]
            return fake_job

        mocker.patch("pipelex.runtime_bridge.bridge.build_pipe_job_from_input", side_effect=spy)
        fake_factory = mocker.patch("pipelex.temporal.tprl_pipe.temporal_pipe_run.make_temporal_pipe_run")
        fake_factory.return_value.run = mocker.AsyncMock(
            return_value=PipeOutput(working_memory=WorkingMemoryFactory.make_empty(), pipeline_run_id="temporal-run-id"),
        )

        await run_pipe_via_bridge(
            PipelexPipeRunInput(pipe_code="fake_pipe", execution_mode=PipelexExecutionMode.TEMPORAL_BLOCKING),
            graph_context=graph_context,
        )

        assert captured["graph_context"] is None
