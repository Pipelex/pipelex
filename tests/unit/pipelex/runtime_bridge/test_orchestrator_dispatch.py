"""The bridge dispatches by orchestration mode through the OrchestratorRegistry (not a match).

Pins the seam independent of the real direct/temporal orchestrators: an arbitrary orchestrator
registered for a token is the one the bridge calls; a token with no registered orchestrator raises
a generic ``MissingOrchestratorError`` naming the token but no orchestrator (D-F).
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.plugins.orchestrator_registry import OrchestratorRegistry
from pipelex.runtime_bridge.bridge import PipelexPipeRunInput, run_pipe_via_bridge
from pipelex.runtime_bridge.delivery_mode import DeliveryMode
from pipelex.runtime_bridge.exceptions import MissingOrchestratorError
from pipelex.runtime_bridge.orchestration_mode import DIRECT_ORCHESTRATION_MODE
from pipelex.runtime_bridge.payloads import PipelexPipeRunOutput


class _FakeOrchestrator:
    supports_fire_and_forget = True

    def __init__(self) -> None:
        self.calls: list[PipeJob] = []

    async def run(self, *, pipe_job: PipeJob, delivery_assignment: object, delivery: DeliveryMode) -> PipelexPipeRunOutput:  # noqa: ARG002
        self.calls.append(pipe_job)
        return PipelexPipeRunOutput(
            output_dict={},
            main_stuff_name=None,
            pipeline_run_id="fake-run",
            workflow_id="fake-wf",
            is_completed=True,
            graph_spec_dump=None,
        )


def _fake_pipe_job(mocker: MockerFixture) -> PipeJob:
    fake_pipe = mocker.MagicMock()
    fake_pipe.code = "fake_pipe"
    fake_pipe.domain_code = "fake_domain"
    return PipeJob.model_construct(
        pipe=fake_pipe,
        working_memory=WorkingMemoryFactory.make_empty(),
        pipe_run_params=PipeRunParamsFactory.make_run_params(),
        job_metadata=JobMetadata(user_id="anonymous", pipeline_run_id="fake-run"),
        library_crate=None,
    )


@pytest.mark.asyncio
class TestOrchestratorDispatch:
    async def test_bridge_routes_mode_to_its_registered_orchestrator(self, mocker: MockerFixture) -> None:
        """The orchestrator registered for the requested mode is the one whose run() the bridge awaits."""
        fake_job = _fake_pipe_job(mocker)
        mocker.patch("pipelex.runtime_bridge.bridge.build_pipe_job_from_input", return_value=fake_job)

        fake_orchestrator = _FakeOrchestrator()
        registry = OrchestratorRegistry({DIRECT_ORCHESTRATION_MODE: fake_orchestrator})
        mocker.patch("pipelex.runtime_bridge.bridge.get_orchestrator_registry", return_value=registry)

        result = await run_pipe_via_bridge(
            PipelexPipeRunInput(pipe_code="fake_pipe", orchestration_mode="direct"),
        )

        assert fake_orchestrator.calls == [fake_job]
        assert result.workflow_id == "fake-wf"

    @pytest.mark.parametrize(
        "mode",
        [
            "temporal",
            "mistralai-workflows",
            "acme",
        ],
    )
    async def test_unregistered_mode_raises_with_generic_plugin_hint(self, mocker: MockerFixture, mode: str) -> None:
        """A token with no registered orchestrator raises a generic MissingOrchestratorError naming the token."""
        fake_job = _fake_pipe_job(mocker)
        mocker.patch("pipelex.runtime_bridge.bridge.build_pipe_job_from_input", return_value=fake_job)
        # Empty registry: no mode is registered, so every token misses.
        mocker.patch("pipelex.runtime_bridge.bridge.get_orchestrator_registry", return_value=OrchestratorRegistry({}))

        with pytest.raises(MissingOrchestratorError) as exc_info:
            await run_pipe_via_bridge(
                PipelexPipeRunInput(pipe_code="fake_pipe", orchestration_mode=mode),
            )

        assert exc_info.value.mode == mode
        assert mode in str(exc_info.value)
        assert "is its plugin installed?" in str(exc_info.value)
