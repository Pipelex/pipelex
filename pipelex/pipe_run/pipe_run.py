from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from pipelex import log
from pipelex.base_exceptions import ErrorReport, PipelexError, PipelexUnexpectedError
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, DeliveryStatus
from pipelex.pipe_run.delivery_executor import DeliveryExecutor
from pipelex.pipe_run.exceptions import DeliveryError
from pipelex.pipe_run.pipe_run_protocol import PipeRunProtocol
from pipelex.pipe_run.tracing_assembly import assemble_tracing_on_output

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
        *,
        delivery_assignment: DeliveryAssignment | None = None,
    ) -> PipeOutput:
        pipeline_run_id: str = pipe_job.job_metadata.run_metadata.pipeline_run_id
        status: DeliveryStatus = DeliveryStatus.COMPLETED
        pipe_output: PipeOutput | None = None
        execution_error: Exception | None = None
        error_report: ErrorReport | None = None

        try:
            pipe_output = await self._pipe_router.run(pipe_job)
            # Stamp the job onto the run's OWN output, here and nowhere else.
            # Only the top-level output crosses a transport boundary; a sub-pipe's
            # output stays in-process, so stamping at every `PipeOutput(...)` site
            # would be noise on ~17 constructors to serve one of them.
            pipe_output.set_job_metadata(job_metadata=pipe_job.job_metadata)
        except Exception as exc:  # ruff: ignore[blind-except]
            # Observe-and-reraise: records FAILED status so the finally delivery sees it, then re-raises the original error below.
            status = DeliveryStatus.FAILED
            execution_error = exc
            # Always build a report for the FAILED webhook: Pipelex errors carry their own
            # classification; a bare exception is wrapped in PipelexUnexpectedError so the
            # webhook still receives an `error` object — matching Temporal mode, where
            # recover_error_report() is total.
            if isinstance(exc, PipelexError):
                error_report = exc.to_error_report()
            else:
                error_report = PipelexUnexpectedError(str(exc) or repr(exc)).to_error_report()
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

            # Assemble graph and/or usage onto pipe_output from the single trace-event read. The two
            # concerns are gated independently: graph events feed the GraphSpec (so a costs-only run does
            # not set an empty GraphSpec, preserving the --no-graph contract), usage events feed the
            # tokens_usages the submitter renders the cost report from.
            trace_context = pipe_job.job_metadata.trace_context
            if pipe_output is not None and trace_context is not None and (trace_context.emit_graph_events or trace_context.emit_usage_events):
                assemble_tracing_on_output(
                    pipe_output=pipe_output,
                    pipeline_run_id=pipeline_run_id,
                    assemble_graph=trace_context.emit_graph_events,
                    assemble_usage=trace_context.emit_usage_events,
                    domain_code=pipe_job.pipe.domain_code,
                    main_pipe_code=pipe_job.pipe.code,
                    run_mode=pipe_job.pipe_run_params.run_mode,
                )

            if delivery_assignment is not None:
                log.debug(f"Executing delivery for pipeline_run_id={pipeline_run_id}, status={status}")
                try:
                    await self._delivery_executor.execute(
                        pipe_output=pipe_output,
                        storage_scope=pipe_job.job_metadata.run_metadata.storage_scope,
                        pipeline_run_id=pipeline_run_id,
                        delivery_assignment=delivery_assignment,
                        status=status,
                        error_report=error_report,
                        request_id=pipe_job.job_metadata.run_metadata.request_id,
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
