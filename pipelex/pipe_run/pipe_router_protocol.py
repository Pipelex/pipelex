from typing import Protocol

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.observer.observer_protocol import ObserverProtocol, PayloadType
from pipelex.pipe_run.pipe_job import PipeJob


class PipeRouterProtocol(Protocol):
    observer_provider: ObserverProtocol

    async def _before_run(
        self,
        pipe_job: PipeJob,
    ) -> None:
        payload: PayloadType = {
            "pipe_job": pipe_job,
        }
        await self.observer_provider.observe_before_run(payload)

    async def _after_successful_run(
        self,
        pipe_job: PipeJob,
        pipe_output: PipeOutput,
    ) -> None:
        payload: PayloadType = {
            "pipe_job": pipe_job,
            "pipe_output": pipe_output,
        }
        await self.observer_provider.observe_after_successful_run(payload)

    async def _after_failing_run(
        self,
        pipe_job: PipeJob,
        error: Exception,
    ) -> None:
        payload: PayloadType = {
            "pipe_job": pipe_job,
            "error": error,
        }
        await self.observer_provider.observe_after_failing_run(payload)

    async def run(
        self,
        pipe_job: PipeJob,
    ) -> PipeOutput:
        await self._before_run(pipe_job)

        try:
            pipe_output = await self._run_pipe_job(pipe_job)
        except Exception as exc:
            await self._after_failing_run(pipe_job, exc)
            raise

        await self._after_successful_run(pipe_job, pipe_output)

        return pipe_output

    async def _run_pipe_job(
        self,
        pipe_job: PipeJob,
    ) -> PipeOutput: ...
