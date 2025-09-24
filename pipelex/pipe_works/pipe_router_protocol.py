from typing import Protocol

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.observer.observer_protocol import ObserverProtocol, PayloadType
from pipelex.pipe_works.pipe_job import PipeJob


class PipeRouterProtocol(Protocol):
    observer_provider: ObserverProtocol

    def __init__(self, observer_provider: ObserverProtocol):
        self.observer_provider = observer_provider

    async def _before_run(
        self,
        pipe_job: PipeJob,
    ) -> None:
        payload: PayloadType = {
            "pipe_job": pipe_job,
        }
        await self.observer_provider.push(payload)

    async def _after_run(
        self,
        pipe_job: PipeJob,
        pipe_output: PipeOutput,
    ) -> None:
        payload: PayloadType = {
            "pipe_job": pipe_job,
            "pipe_output": pipe_output,
        }
        await self.observer_provider.push(payload)

    async def run(
        self,
        pipe_job: PipeJob,
    ) -> PipeOutput:
        await self._before_run(pipe_job)

        pipe_output: PipeOutput = await self._run_pipe_job(pipe_job)

        await self._after_run(pipe_job, pipe_output)

        return pipe_output

    async def _run_pipe_job(
        self,
        pipe_job: PipeJob,
    ) -> PipeOutput: ...
