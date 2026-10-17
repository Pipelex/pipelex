from __future__ import annotations

import time
from typing import TYPE_CHECKING

from typing_extensions import override

from pipelex import log
from pipelex.base_exceptions import ErrorReport, PipelexError, PipelexUnexpectedError
from pipelex.errors.security_event import emit_security_event_for_run
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.interpreter_hub import get_concept_library, get_own_pipes
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, DeliveryStatus
from pipelex.pipe_run.delivery_executor import DeliveryExecutor
from pipelex.pipe_run.exceptions import DeliveryError
from pipelex.pipe_run.pipe_run_protocol import PipeRunProtocol
from pipelex.pipe_run.tracing_assembly import RunTraceEvents, assemble_tracing_on_output, read_run_trace_events
from pipelex.pipeline.build_pipe_io_artifacts import build_pipe_io_artifacts
from pipelex.pipeline.usage_stats_reporting import RunUsageFacts, input_kinds_of, report_run_usage
from pipelex.system.usage_stats.usage_stats_client import usage_stats_are_enabled
from pipelex.system.usage_stats.usage_stats_contract import UsageStatsOutcome
from pipelex.system.usage_stats.usage_stats_runs import RunInferenceTally, tallying_inference_calls
from pipelex.tools.log.error_fields import error_fields

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.graph.graphspec import GraphSpec
    from pipelex.pipe_run.pipe_job import PipeJob
    from pipelex.pipe_run.pipe_router_protocol import PipeRouterProtocol


class PipeRun(PipeRunProtocol):
    """Direct-mode PipeRun: executes the pipe inline, then delivers results."""

    def __init__(self, pipe_router: PipeRouterProtocol, *, reports_usage_stats: bool = True) -> None:
        """Execute pipes through `pipe_router`.

        Args:
            pipe_router: The router the run's pipes are dispatched through.
            reports_usage_stats: Whether a run reports its anonymous usage statistics, its `run_completed` and
                `model_used` events, when statistics are on. Off for the runs a validation makes, which its own
                `method_validated` describes.
        """
        self._pipe_router = pipe_router
        self._delivery_executor = DeliveryExecutor()
        self._reports_usage_stats = reports_usage_stats

    @override
    async def run(
        self,
        pipe_job: PipeJob,
        *,
        delivery_assignment: DeliveryAssignment | None = None,
    ) -> PipeOutput:
        # The run's identifiers ride the payload; here is where a direct-mode run binds them onto every
        # record it emits, the delivery's included. The binding is released when the run returns.
        with pipe_job.job_metadata.log_context():
            try:
                return await self._run_bound(pipe_job=pipe_job, delivery_assignment=delivery_assignment)
            except PipelexError as exc:
                # This run owns the security events of the refusals raised while it executes, in this process; the runner
                # that dispatched it logs none. A refusal its pipes raised was logged already; one its tail raised, such as a
                # webhook the SSRF guard refuses at fire time after the run completed, is logged here.
                emit_security_event_for_run(error=exc, run_metadata=pipe_job.job_metadata.run_metadata)
                raise

    async def _run_bound(
        self,
        *,
        pipe_job: PipeJob,
        delivery_assignment: DeliveryAssignment | None,
    ) -> PipeOutput:
        pipeline_run_id: str = pipe_job.job_metadata.run_metadata.pipeline_run_id
        status: DeliveryStatus = DeliveryStatus.COMPLETED
        pipe_output: PipeOutput | None = None
        execution_error: Exception | None = None
        error_report: ErrorReport | None = None
        closed_graph: GraphSpec | None = None
        # The run's statistics: its inputs are read before the run adds its own outputs to its working memory.
        usage_tally = RunInferenceTally() if self._reports_usage_stats and usage_stats_are_enabled() else None
        input_kinds = input_kinds_of(working_memory=pipe_job.working_memory) if usage_tally is not None else (False, False)
        started_at = time.monotonic()

        try:
            with tallying_inference_calls(tally=usage_tally):
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
            # The error rides as fields and no traceback: the exception is re-raised below, and its traceback
            # belongs to whoever catches it, the CLI or the API's handler, which would otherwise print it twice.
            # `pipe_code` is the bare code `Pipe run starts` carries for the same pipe, so one query finds both lines.
            log.error(
                "The execution of a pipe failed",
                fields={"pipe_code": pipe_job.pipe.code, "pipe_ref": pipe_job.pipe.pipe_ref, **error_fields(exc=exc)},
            )
            # A security refusal also logs its security event, once, naming the run and never what it refused.
            emit_security_event_for_run(error=exc, run_metadata=pipe_job.job_metadata.run_metadata)
        finally:
            tracer_manager = GraphTracerManager.get_instance()
            if tracer_manager is not None:
                try:
                    closed_graph = tracer_manager.close_tracer(pipeline_run_id)
                except OSError as close_error:
                    if execution_error is None:
                        raise
                    # A secondary failure rides as fields with no traceback: the execution error is chained onto it, so
                    # its traceback would print the execution error's text, which can quote the run's inputs.
                    log.error(
                        "The graph tracer could not be closed after the pipe execution failed",
                        fields=error_fields(exc=close_error),
                    )

            # Assemble graph and/or usage onto pipe_output from the single trace-event read. The two
            # concerns are gated independently: graph events feed the GraphSpec (so a costs-only run does
            # not set an empty GraphSpec, preserving the --no-graph contract), usage events feed the
            # tokens_usages the submitter renders the cost report from.
            # The run's statistics read the same events, its usage events, whether the run completed or not.
            trace_context = pipe_job.job_metadata.trace_context
            assembles_output = (
                pipe_output is not None and trace_context is not None and (trace_context.emit_graph_events or trace_context.emit_usage_events)
            )
            counts_usage = usage_tally is not None and trace_context is not None and trace_context.emit_usage_events
            trace_events: RunTraceEvents | None = None
            if assembles_output or counts_usage:
                trace_events = read_run_trace_events(pipeline_run_id=pipeline_run_id)
            if pipe_output is not None and trace_context is not None and assembles_output:
                assemble_tracing_on_output(
                    pipe_output=pipe_output,
                    pipeline_run_id=pipeline_run_id,
                    assemble_graph=trace_context.emit_graph_events,
                    assemble_usage=trace_context.emit_usage_events,
                    domain_code=pipe_job.pipe.domain_code,
                    main_pipe_code=pipe_job.pipe.code,
                    trace_events=trace_events,
                )
                if trace_context.describe_pipe_io and pipe_output.graph_spec is not None:
                    self._build_pipe_io_artifacts_on_output(pipe_output=pipe_output, pipeline_run_id=pipeline_run_id)

            if usage_tally is not None:
                outcome: UsageStatsOutcome
                if execution_error is not None:
                    outcome = UsageStatsOutcome.FAILED
                elif pipe_output is None:
                    # Neither a result nor an exception: the run was cancelled or interrupted, which no `except Exception` catches.
                    outcome = UsageStatsOutcome.CANCELLED
                else:
                    outcome = UsageStatsOutcome.SUCCEEDED
                self._report_usage_stats(
                    pipe_job=pipe_job,
                    outcome=outcome,
                    execution_error=execution_error,
                    duration_seconds=time.monotonic() - started_at,
                    input_kinds=input_kinds,
                    trace_events=trace_events if counts_usage else None,
                    closed_graph=closed_graph,
                    usage_tally=usage_tally,
                )

            if delivery_assignment is not None:
                log.debug("Executing the delivery", fields={"delivery_status": status})
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
                    # As fields with no traceback, for the same reason as the tracer's: the execution error is chained onto it.
                    log.error(
                        "The delivery also failed after the pipe execution failed",
                        fields=error_fields(exc=delivery_error),
                    )

        if execution_error is not None:
            raise execution_error

        assert pipe_output is not None
        return pipe_output

    @classmethod
    def _report_usage_stats(
        cls,
        *,
        pipe_job: PipeJob,
        outcome: UsageStatsOutcome,
        execution_error: Exception | None,
        duration_seconds: float,
        input_kinds: tuple[bool, bool],
        trace_events: RunTraceEvents | None,
        closed_graph: GraphSpec | None,
        usage_tally: RunInferenceTally,
    ) -> None:
        """Record the run's `run_completed`, and a `model_used` per model when its usage events were read.

        Runs inside the run's library window, which the bundle's description reads. It runs in the `finally` ahead of
        the delivery, and an anonymous statistic must never replace a run's outcome or skip its delivery, so a failure
        to build it is logged at debug level and the event is not sent.
        """
        has_image_input, has_document_input = input_kinds
        try:
            report_run_usage(
                facts=RunUsageFacts(
                    outcome=outcome,
                    error=execution_error,
                    is_dry_run=pipe_job.pipe_run_params.run_mode.is_dry,
                    duration_seconds=duration_seconds,
                    main_pipe=pipe_job.pipe,
                    own_pipes=get_own_pipes(),
                    own_concepts=get_concept_library().list_own_concepts(),
                    has_image_input=has_image_input,
                    has_document_input=has_document_input,
                    events=trace_events.events if trace_events is not None else None,
                    closed_graph=closed_graph,
                    tally=usage_tally,
                )
            )
        except (PipelexError, ValueError, OSError) as report_error:
            # A library that cannot describe the bundle, an event that will not validate, a state that cannot be read.
            log.debug("The usage statistics of a run could not be built", fields=error_fields(exc=report_error))

    @classmethod
    def _build_pipe_io_artifacts_on_output(cls, *, pipe_output: PipeOutput, pipeline_run_id: str) -> None:
        """Describe the graph's data: build the three I/O artifacts over the run library's own pipes and set them on the output.

        Runs inside the run's library window — `PipelineRunner.execute` tears the run library down
        after this returns, and the builders need it — and before the direct-mode delivery below,
        which writes the artifacts beside the graphspec. The scope is the library's own pipes, as
        validate's is: a dependency package's pipes are keyed by alias in the library but by bare
        `pipe_ref` in the artifacts, where they would collide with the host's, and the host's crate
        holds no blueprint of theirs to describe them from. Best-effort like the graph assembly, and
        blind on purpose: this runs in the `finally` ahead of the delivery, so an exception that
        escaped here would replace the run's own outcome and skip the delivery of a run that
        completed. Whatever the builders raise — a contract that will not render, a crate that
        will not normalize, a protocol model that will not validate, or a bug of their own — is
        reported on `pipe_io_artifacts_error` and the run keeps its result.
        """
        try:
            pipe_output.pipe_io_artifacts = build_pipe_io_artifacts(get_own_pipes())
        except Exception as build_error:  # ruff: ignore[blind-except]
            log.warning("The I/O artifacts of a run could not be built", fields=error_fields(exc=build_error))
            pipe_output.pipe_io_artifacts_error = f"Failed to build the I/O artifacts for pipeline_run_id={pipeline_run_id}: {build_error}"
