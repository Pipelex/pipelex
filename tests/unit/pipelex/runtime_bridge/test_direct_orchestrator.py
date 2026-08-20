from typing import TYPE_CHECKING, cast

import pytest

from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.runtime_bridge.direct_orchestrator import DirectOrchestrator
from pipelex.runtime_bridge.exceptions import PipelexBridgeDispatchError
from pipelex.system.job_metadata import JobMetadata, RunMetadata

if TYPE_CHECKING:
    from pipelex.pipe_machinery.pipe_abstract import PipeAbstract


class _StubPipe:
    """Minimal stand-in — DirectOrchestrator.start() only reads pipe_job.pipe.code for its error message."""

    code = "direct_test_pipe"


def _make_pipe_job() -> PipeJob:
    """Build a PipeJob via model_construct to bypass pipe validation (start() never runs the pipe)."""
    return PipeJob.model_construct(
        pipe=cast("PipeAbstract", _StubPipe()),
        working_memory=None,
        working_memory_raw=None,
        pipe_run_params=PipeRunParamsFactory.make_run_params(),
        job_metadata=JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", user_id="test-user", pipeline_run_id="test-run")),
        output_name=None,
        library_crate=None,
    )


class TestDirectOrchestratorStart:
    def test_does_not_support_fire_and_forget(self) -> None:
        """DIRECT is in-process only, so it must advertise no genuine async path."""
        assert DirectOrchestrator().supports_fire_and_forget is False

    @pytest.mark.asyncio
    async def test_start_raises_dispatch_error(self) -> None:
        """start() is unreachable behind the supports_fire_and_forget gate; called directly it must fail loudly, never ack."""
        orchestrator = DirectOrchestrator()
        with pytest.raises(PipelexBridgeDispatchError, match="supports_fire_and_forget"):
            await orchestrator.start(pipe_job=_make_pipe_job(), delivery_assignment=None)
