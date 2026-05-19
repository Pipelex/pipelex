from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from pipelex import log
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, DeliveryStatus
from pipelex.pipe_run.delivery_executor import DeliveryExecutor
from pipelex.pipe_run.exceptions import DeliveryError
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
    ) -> PipeOutput:
        pipeline_run_id: str = pipe_job.job_metadata.pipeline_run_id
        status: DeliveryStatus = DeliveryStatus.COMPLETED
        pipe_output: PipeOutput | None = None
        execution_error: Exception | None = None

        try:
            pipe_output = await self._pipe_router.run(pipe_job)
        except Exception as exc:  # noqa: BLE001
            # Observe-and-reraise: records FAILED status so the finally delivery sees it, then re-raises the original error below.
            status = DeliveryStatus.FAILED
            execution_error = exc
            log.error(f"Pipe execution failed for pipeline_run_id={pipeline_run_id}: {exc}")
        finally:
            tracer_manager = GraphTracerManager.get_instance()
            if tracer_manager is not None:
                try:
                    tracer_manager.close_tracer(pipeline_run_id)
                except OSError as tracer_close_error:
                    if execution_error is None:
                        raise
                    log.error(
                        f"close_tracer also failed for pipeline_run_id={pipeline_run_id} "
                        f"after pipe execution failure; raising original execution error. "
                        f"Suppressed tracer close error: {tracer_close_error}"
                    )

            if pipe_output is not None:
                assemble_graph_on_output(
                    pipe_output=pipe_output,
                    pipeline_run_id=pipeline_run_id,
                    domain_code=pipe_job.pipe.domain_code,
                    main_pipe_code=pipe_job.pipe.code,
                )

            if delivery_assignment is not None:
                log.debug(f"Executing delivery for pipeline_run_id={pipeline_run_id}, status={status}")
                try:
                    await self._delivery_executor.execute(
                        pipe_output=pipe_output,
                        user_id=pipe_job.job_metadata.user_id,
                        pipeline_run_id=pipeline_run_id,
                        delivery_assignment=delivery_assignment,
                        status=status,
                    )
                except DeliveryError as delivery_error:
                    if execution_error is None:
                        raise
                    log.error(
                        f"Delivery also failed for pipeline_run_id={pipeline_run_id} "
                        f"after pipe execution failure; raising original execution error. "
                        f"Suppressed delivery error: {delivery_error}"
                    )

        if execution_error is not None:
            raise execution_error

        assert pipe_output is not None
        return pipe_output
