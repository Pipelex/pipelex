from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from pipelex import log
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, DeliveryStatus, StorageTarget
from pipelex.pipe_run.delivery_executor import DeliveryExecutor
from pipelex.pipe_run.graph_assembly import assemble_graph_on_output
from pipelex.pipe_run.pipe_run_protocol import PipeRunProtocol

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.pipe_run.pipe_job import PipeJob
    from pipelex.pipe_run.pipe_router_protocol import PipeRouterProtocol


class PipeRun(PipeRunProtocol):
    """Direct-mode PipeRun: executes the pipe inline, then delivers results."""

    def __init__(self, pipe_router: PipeRouterProtocol) -> None:
        self._pipe_router = pipe_router
        self._delivery_executor = DeliveryExecutor()

    @override
    async def run(
        self,
        pipe_job: PipeJob,
        delivery_assignment: DeliveryAssignment | None = None,
        wfid: str | None = None,
    ) -> PipeOutput:
        pipeline_run_id: str = pipe_job.job_metadata.pipeline_run_id
        status: DeliveryStatus = DeliveryStatus.COMPLETED
        pipe_output: PipeOutput | None = None
        execution_error: Exception | None = None

        try:
            pipe_output = await self._pipe_router.run(pipe_job, wfid=wfid)
        except Exception as exc:
            # TODO: use a "finally" block
            status = DeliveryStatus.FAILED
            execution_error = exc
            log.error(f"Pipe execution failed for pipeline_run_id={pipeline_run_id}: {exc}")

        # Close graph tracer (flushes in-memory nodes to the event log)
        tracer_manager = GraphTracerManager.get_instance()
        if tracer_manager is not None:
            tracer_manager.close_tracer(pipeline_run_id)

        # Assemble full graph from trace events
        if pipe_output is not None:
            assemble_graph_on_output(
                pipe_output=pipe_output,
                pipeline_run_id=pipeline_run_id,
                domain_code=pipe_job.pipe.domain_code,
                main_pipe_code=pipe_job.pipe.code,
            )

        # Deliver results — always. Default to storage-only if no assignment provided.
        if delivery_assignment is None:
            delivery_assignment = DeliveryAssignment(storage=StorageTarget())
        log.debug(f"Executing delivery for pipeline_run_id={pipeline_run_id}, status={status}")
        await self._delivery_executor.execute(
            pipe_output=pipe_output,
            user_id=pipe_job.job_metadata.user_id,
            pipeline_run_id=pipeline_run_id,
            delivery_assignment=delivery_assignment,
            status=status,
        )

        # Re-raise after delivery so the caller sees the error
        if execution_error is not None:
            raise execution_error

        assert pipe_output is not None
        return pipe_output
