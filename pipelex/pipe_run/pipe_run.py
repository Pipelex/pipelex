from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from pipelex import log
from pipelex.pipe_run.delivery_executor import execute_delivery
from pipelex.pipe_run.pipe_run_protocol import PipeRunProtocol

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
    from pipelex.pipe_run.pipe_job import PipeJob
    from pipelex.pipe_run.pipe_router_protocol import PipeRouterProtocol


class PipeRun(PipeRunProtocol):
    """Direct-mode PipeRun: executes the pipe inline, then delivers results."""

    def __init__(self, pipe_router: PipeRouterProtocol) -> None:
        self._pipe_router = pipe_router

    @override
    async def run(
        self,
        pipe_job: PipeJob,
        delivery_assignment: DeliveryAssignment | None = None,
        wfid: str | None = None,
    ) -> PipeOutput:
        pipe_output = await self._pipe_router.run(pipe_job, wfid=wfid)

        if delivery_assignment is not None:
            pipeline_run_id: str = pipe_job.job_metadata.pipeline_run_id
            log.debug(f"Executing delivery for pipeline_run_id={pipeline_run_id}")
            await execute_delivery(
                pipe_output=pipe_output,
                pipeline_run_id=pipeline_run_id,
                delivery_assignment=delivery_assignment,
            )

        return pipe_output
