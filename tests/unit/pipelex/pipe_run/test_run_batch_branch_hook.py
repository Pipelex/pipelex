"""The `run_batch_branch` router hook: its default body IS the behavior for in-process routers.

`PipeBatch` marks its per-item fan-out dispatches by calling this hook instead of `run`. Every
router that has no isolation to offer inherits the concrete default, which delegates straight to
`run` — so adding the hook changed no in-process behavior. These tests pin that delegation, because
a distributed router's override is only correct if the un-overridden case stays a plain run.
"""

from typing import TYPE_CHECKING, cast

import pytest
from typing_extensions import override

from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.observer.observer_protocol import ObserverNoOp
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_router_protocol import PipeRouterProtocol
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode

if TYPE_CHECKING:
    from pipelex.pipe_machinery.pipe_abstract import PipeAbstract


class _StubPipe:
    """Minimal pipe stand-in: the router only reads `.code` off it."""

    code = "stub_pipe"


class _RecordingRouter(PipeRouterProtocol):
    """Router that records the jobs reaching `_run_pipe_job` and never touches a real pipe."""

    def __init__(self) -> None:
        self.observer = ObserverNoOp()
        self.dispatched_jobs: list[PipeJob] = []

    @override
    async def _run_pipe_job(self, pipe_job: PipeJob) -> PipeOutput:
        self.dispatched_jobs.append(pipe_job)
        return PipeOutput(
            working_memory=WorkingMemoryFactory.make_empty(),
            pipeline_run_id=pipe_job.job_metadata.run_metadata.pipeline_run_id,
        )


def _make_pipe_job() -> PipeJob:
    return PipeJob.model_construct(
        pipe=cast("PipeAbstract", _StubPipe()),
        working_memory=None,
        working_memory_raw=None,
        pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE),
        job_metadata=JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", user_id="test-user", pipeline_run_id="test-run")),
        output_name=None,
        library_crate=None,
    )


@pytest.mark.asyncio(loop_scope="class")
class TestRunBatchBranchHook:
    async def test_default_delegates_to_run(self) -> None:
        """The un-overridden hook reaches `_run_pipe_job` with the very job it was handed."""
        router = _RecordingRouter()
        pipe_job = _make_pipe_job()

        await router.run_batch_branch(pipe_job)

        assert router.dispatched_jobs == [pipe_job]

    async def test_default_runs_the_observer_hooks_like_run(self) -> None:
        """Delegation goes through `run`, not around it — so observers still see the branch.

        Pins the "delegate to `run`" contract rather than "delegate to `_run_pipe_job`": a hook that
        short-circuited to the private dispatch would silently drop every batch branch out of the
        observer stream.
        """
        observed: list[str] = []

        class _ObservingRouter(_RecordingRouter):
            @override
            async def _before_run(self, pipe_job: PipeJob) -> None:
                observed.append("before")

            @override
            async def _after_successful_run(self, pipe_job: PipeJob, *, pipe_output: PipeOutput) -> None:
                observed.append("after")

        router = _ObservingRouter()

        await router.run_batch_branch(_make_pipe_job())

        assert observed == ["before", "after"]
