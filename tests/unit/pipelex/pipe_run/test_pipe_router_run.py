from typing import TYPE_CHECKING, cast

import pytest
from typing_extensions import override

from pipelex.cogt.exceptions import CogtError, InferenceErrorCategory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.observer.observer_protocol import ObserverNoOp
from pipelex.pipe_run.exceptions import PipeRouterError, PipeRunError
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_router_protocol import PipeRouterProtocol
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_abstract import PipeAbstract


class _StubPipe:
    """Minimal pipe stand-in: the router only reads `.code` off it."""

    code = "stub_pipe"


class _StubPipeRouter(PipeRouterProtocol):
    """Router whose `_run_pipe_job` always raises a scripted error and counts its calls."""

    def __init__(self, error: Exception):
        self.observer = ObserverNoOp()
        self._error = error
        self.call_count = 0

    @override
    async def _run_pipe_job(self, pipe_job: PipeJob) -> PipeOutput:
        self.call_count += 1
        raise self._error


def _make_pipe_job() -> PipeJob:
    return PipeJob.model_construct(
        pipe=cast("PipeAbstract", _StubPipe()),
        working_memory=None,
        working_memory_raw=None,
        pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE),
        job_metadata=JobMetadata(user_id="test-user", pipeline_run_id="test-run"),
        output_name=None,
        library_crate=None,
    )


@pytest.mark.asyncio(loop_scope="class")
class TestPipeRouterRun:
    async def test_transient_cogt_error_surfaces_on_first_attempt(self) -> None:
        """Direct execution is a single pipeline-level attempt: a transient CogtError is not retried.

        Pins the "direct = single attempt" contract against a future re-introduction of a retry loop.
        """
        error = CogtError(message="rate limited", error_category=InferenceErrorCategory.TRANSIENT)
        router = _StubPipeRouter(error=error)

        with pytest.raises(CogtError) as exc_info:
            await router.run(_make_pipe_job())

        assert exc_info.value is error
        assert router.call_count == 1

    async def test_pipe_run_error_wraps_as_pipe_router_error(self) -> None:
        """A PipeRunError surfaces as a PipeRouterError carrying the pipe-stack context.

        Pins the "keep the handler" contract against a future accidental deletion of the
        error-propagation handler in `run()`.
        """
        pipe_run_error = PipeRunError(message="bad pipe", run_mode=PipeRunMode.LIVE, pipe_code="stub_pipe")
        router = _StubPipeRouter(error=pipe_run_error)

        with pytest.raises(PipeRouterError) as exc_info:
            await router.run(_make_pipe_job())

        assert exc_info.value.__cause__ is pipe_run_error
        assert exc_info.value.pipe_code == "stub_pipe"
        assert exc_info.value.pipe_stack == ["stub_pipe"]
        assert router.call_count == 1
