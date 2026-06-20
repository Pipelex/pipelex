import pytest
from pytest_mock import MockerFixture

from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.runtime_bridge.bridge import PipelexPipeRunInput, run_pipe_via_bridge
from pipelex.runtime_bridge.exceptions import MissingOrchestratorError
from pipelex.runtime_bridge.execution_mode import PipelexExecutionMode


def _make_fake_pipe_job(mocker: MockerFixture, pipe_code: str, pipeline_run_id: str) -> PipeJob:
    """Build a PipeJob without triggering Pydantic's PipeAbstract validation.

    Tests at the dispatch layer don't care about the concrete pipe — only
    that the bridge routes the right pipe_job to the right PipeRun. Using
    ``model_construct`` lets us pass a MagicMock as ``pipe`` without
    constructing a full PipeAbstract subclass.
    """
    fake_pipe = mocker.MagicMock()
    fake_pipe.code = pipe_code
    fake_pipe.domain_code = "fake_domain"
    return PipeJob.model_construct(
        pipe=fake_pipe,
        working_memory=WorkingMemoryFactory.make_empty(),
        pipe_run_params=PipeRunParamsFactory.make_run_params(),
        job_metadata=JobMetadata(user_id="anonymous", pipeline_run_id=pipeline_run_id),
        library_crate=None,
    )


@pytest.mark.asyncio
class TestDispatch:
    async def test_direct_mode_calls_pipe_run_with_pipe_job(self, mocker: MockerFixture) -> None:
        fake_job = _make_fake_pipe_job(mocker=mocker, pipe_code="fake_pipe", pipeline_run_id="caller-run-id")
        mocker.patch(
            "pipelex.runtime_bridge.bridge.build_pipe_job_from_input",
            return_value=fake_job,
        )

        fake_output = PipeOutput(
            working_memory=WorkingMemoryFactory.make_empty(),
            pipeline_run_id="injected-run-id",
        )
        mock_run = mocker.patch.object(PipeRun, "run", new_callable=mocker.AsyncMock, return_value=fake_output)

        result = await run_pipe_via_bridge(
            PipelexPipeRunInput(
                pipe_code="fake_pipe",
                execution_mode=PipelexExecutionMode.DIRECT,
                pipeline_run_id="caller-run-id",
            )
        )

        assert mock_run.await_count == 1
        await_args = mock_run.await_args
        assert await_args is not None
        call_kwargs: dict[str, object] = dict(await_args.kwargs)
        assert call_kwargs["delivery_assignment"] is None
        assert call_kwargs["pipe_job"] is fake_job

        assert result.is_completed is True
        assert result.pipeline_run_id == "injected-run-id"
        assert result.workflow_id is None
        assert result.graph_spec_dump is None

    async def test_mistral_native_without_plugin_raises_with_install_hint(self, mocker: MockerFixture) -> None:
        fake_job = _make_fake_pipe_job(mocker=mocker, pipe_code="fake_pipe", pipeline_run_id="caller-run-id")
        mocker.patch(
            "pipelex.runtime_bridge.bridge.build_pipe_job_from_input",
            return_value=fake_job,
        )

        # MISTRAL_NATIVE is contributed by the external pipelex-mistralai-workflows plugin, which is
        # not installed in core's test env — so the orchestrator registry has no entry for it and the
        # bridge raises MissingOrchestratorError, which maps the mode to its exact install hint.
        with pytest.raises(MissingOrchestratorError) as exc_info:
            await run_pipe_via_bridge(
                PipelexPipeRunInput(
                    pipe_code="fake_pipe",
                    execution_mode=PipelexExecutionMode.MISTRAL_NATIVE,
                )
            )

        assert exc_info.value.mode is PipelexExecutionMode.MISTRAL_NATIVE
        assert "pipelex-mistralai-workflows" in str(exc_info.value)
        assert "pip install" in str(exc_info.value)
