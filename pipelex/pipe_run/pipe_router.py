from typing_extensions import override

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.observer.observer_protocol import ObserverNoOp, ObserverProtocol
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_router_protocol import PipeRouterProtocol


class PipeRouter(PipeRouterProtocol):
    def __init__(self, observer_provider: ObserverProtocol | None = None):
        self.observer_provider = observer_provider or ObserverNoOp()

    @override
    async def _run_pipe_job(
        self,
        pipe_job: PipeJob,
    ) -> PipeOutput:
        return await pipe_job.pipe.run_pipe(
            job_metadata=pipe_job.job_metadata,
            working_memory=pipe_job.working_memory,
            output_name=pipe_job.output_name,
            pipe_run_params=pipe_job.pipe_run_params,
        )
