"""The bridge dispatches by execution mode through the OrchestratorRegistry (not a match).

Pins the seam independent of the real DIRECT/Temporal orchestrators: an arbitrary orchestrator
registered for a mode is the one the bridge calls; a mode with no registered orchestrator raises
``MissingOrchestratorError`` carrying that mode's exact install hint (per-mode error parity, C7).
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.plugins.orchestrator_registry import OrchestratorRegistry
from pipelex.runtime_bridge.bridge import PipelexPipeRunInput, run_pipe_via_bridge
from pipelex.runtime_bridge.exceptions import MissingOrchestratorError
from pipelex.runtime_bridge.execution_mode import PipelexExecutionMode
from pipelex.runtime_bridge.payloads import PipelexPipeRunOutput


class _FakeOrchestrator:
    def __init__(self) -> None:
        self.calls: list[PipeJob] = []

    async def run(self, *, pipe_job: PipeJob, delivery_assignment: object) -> PipelexPipeRunOutput:  # noqa: ARG002
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
        registry = OrchestratorRegistry({PipelexExecutionMode.DIRECT: fake_orchestrator})
        mocker.patch("pipelex.runtime_bridge.bridge.get_orchestrator_registry", return_value=registry)

        result = await run_pipe_via_bridge(
            PipelexPipeRunInput(pipe_code="fake_pipe", execution_mode=PipelexExecutionMode.DIRECT),
        )

        assert fake_orchestrator.calls == [fake_job]
        assert result.workflow_id == "fake-wf"

    @pytest.mark.parametrize(
        ("mode", "hint_fragment"),
        [
            (PipelexExecutionMode.TEMPORAL_BLOCKING, "pip install 'pipelex[temporal]'"),
            (PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET, "pip install 'pipelex[temporal]'"),
            (PipelexExecutionMode.MISTRAL_NATIVE, "pip install pipelex-mistralai-workflows"),
        ],
    )
    async def test_unregistered_mode_raises_with_its_exact_hint(self, mocker: MockerFixture, mode: PipelexExecutionMode, hint_fragment: str) -> None:
        """A mode with no registered orchestrator raises MissingOrchestratorError with that mode's install hint."""
        fake_job = _fake_pipe_job(mocker)
        mocker.patch("pipelex.runtime_bridge.bridge.build_pipe_job_from_input", return_value=fake_job)
        # Empty registry: no mode is registered, so every mode misses.
        mocker.patch("pipelex.runtime_bridge.bridge.get_orchestrator_registry", return_value=OrchestratorRegistry({}))

        # TEMPORAL_FIRE_AND_FORGET validates a delivery target before dispatch; supply one so the test
        # exercises the registry miss, not the delivery-validation guard.
        delivery_dump = {"webhooks": [{"url": "https://example.test/hook"}], "storage": None}
        with pytest.raises(MissingOrchestratorError) as exc_info:
            await run_pipe_via_bridge(
                PipelexPipeRunInput(pipe_code="fake_pipe", execution_mode=mode, delivery_assignment_dump=delivery_dump),
            )

        assert exc_info.value.mode is mode
        assert hint_fragment in str(exc_info.value)
