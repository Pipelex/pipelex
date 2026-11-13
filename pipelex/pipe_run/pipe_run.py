from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from mthds.protocol.problem.registry import CoreCode
from typing_extensions import override

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.errors.problem import PipelexProblem, ProblemView, make_problem, problem_status_of
from pipelex.errors.security_event import emit_security_event_for_run
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.interpreter_hub import get_concept_library, get_own_pipes
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, DeliveryStatus
from pipelex.pipe_run.delivery_executor import DeliveryExecutor, run_problem_of
from pipelex.pipe_run.exceptions import DeliveryError
from pipelex.pipe_run.located_failure import reported_failure_code
from pipelex.pipe_run.pipe_run_protocol import PipeRunProtocol
from pipelex.pipe_run.tracing_assembly import RunTraceEvents, assemble_tracing_on_output, read_run_trace_events
from pipelex.pipeline.build_pipe_io_artifacts import build_pipe_io_artifacts
from pipelex.pipeline.usage_stats_reporting import RunUsageFacts, input_kinds_of, report_run_usage
from pipelex.system.error_tracking.error_report import ErrorReportKind, operator_problem_of
from pipelex.system.error_tracking.error_tracking import has_error_trackers, reaches_error_trackers, report_exception
from pipelex.system.usage_stats.usage_stats_client import usage_stats_are_enabled
from pipelex.system.usage_stats.usage_stats_contract import UsageStatsOutcome
from pipelex.system.usage_stats.usage_stats_runs import RunInferenceTally, tallying_inference_calls
from pipelex.tools.log.error_fields import ERROR_CODE_FIELD, ERROR_TYPE_FIELD, error_fields
from pipelex.tools.network.exceptions import SsrfBlockedError

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.graph.graphspec import GraphSpec
    from pipelex.pipe_run.pipe_job import PipeJob
    from pipelex.pipe_run.pipe_router_protocol import PipeRouterProtocol


def _secondary_failure_fields(*, exc: Exception) -> dict[str, str]:
    """The fields of a failure that followed the pipe's own, by its class and, for a Pipelex error, its code.

    Like the line about the pipe's failure, a line about what failed after it never carries the exception's text: a
    delivery's names the caller's webhook URL or the place it stored to, and an ``OSError``'s the file it could not
    close, each the run's data.
    """
    fields = {ERROR_TYPE_FIELD: type(exc).__name__}
    if isinstance(exc, PipelexError):
        fields[ERROR_CODE_FIELD] = str(exc.resolve_error_code())
    return fields


def _failure_code(*, error: Exception) -> str:
    """The registry code a run's failure reports, read without building its problem, which only a webhook needs.

    A bare exception stands as a fault of ours, ``runtime.unexpected``. A Pipelex error reports the code its cause chain
    resolves to, or, when its root fault carries a problem recovered across a transport boundary, that problem's code,
    as the problem the caller receives does.
    """
    if not isinstance(error, PipelexError):
        return CoreCode.RUNTIME_UNEXPECTED
    return reported_failure_code(failure=error)


def _cancelled_run_problem(*, pipeline_run_id: str, request_id: str | None) -> PipelexProblem:
    """The problem a cancelled run's webhooks receive: ``run.cancelled``, since a cancelled run ends failed."""
    return make_problem(code=CoreCode.RUN_CANCELLED, view=ProblemView.OPERATOR, pipeline_run_id=pipeline_run_id, request_id=request_id)


class PipeRun(PipeRunProtocol):
    """Direct-mode PipeRun: executes the pipe inline, then delivers results."""

    def __init__(self, pipe_router: PipeRouterProtocol, *, reports_usage_stats: bool = True, reports_errors: bool = True) -> None:
        """Execute pipes through `pipe_router`.

        Args:
            pipe_router: The router the run's pipes are dispatched through.
            reports_usage_stats: Whether a run reports its anonymous usage statistics, its `run_completed` and
                `model_used` events, when statistics are on. Off for the runs a validation makes, which its own
                `method_validated` describes.
            reports_errors: Whether a failed run is reported to the installed error trackers, when its failure is the
                operator's to fix and the run is no dry run. Off for the runs a validation makes, whose failures are
                the validation's findings about the method, answered to whoever asked for it.
        """
        self._pipe_router = pipe_router
        self._delivery_executor = DeliveryExecutor()
        self._reports_usage_stats = reports_usage_stats
        self._reports_errors = reports_errors

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

    def _report_run_failure(self, *, error: Exception, pipe_job: PipeJob, webhook_problem: PipelexProblem | None) -> None:
        """Report a failed run to the operator's error trackers, when its failure is the operator's to fix.

        The report carries the operator's problem, the run's ids and its pipe. A validation's run, whose failures are
        its findings about the method, and a dry run report nothing, nor does a failure the server has nothing to fix
        for, weighed by its problem's status and domain as the API server weighs the same failure
        (``reaches_error_trackers``): a caller's mistake, or a ``501`` saying this deployment does not offer what the
        run asked for, which the caller meets on every run that asks. With no tracker installed nothing is built.
        Reported once, and marked so: a host that lets the error reach the interpreter's hook or answers it, or raises
        its own from it, does not report it again.

        Args:
            error: The error that escapes the run, which its caller receives: the pipe's own, or one its tail raised
                after the pipe executed, which replaced it, such as the tracer that would not close or the delivery
                that failed. Or the pipe's own error when an interruption, such as a cancellation, arrives during the
                tail and replaces it, which no `except Exception` sees.
            pipe_job: The run's job.
            webhook_problem: The problem built for the run's webhooks, when it has any, which is reused.
        """
        if not self._reports_errors or not has_error_trackers() or pipe_job.pipe_run_params.run_mode.is_dry:
            return
        run_metadata = pipe_job.job_metadata.run_metadata
        problem = webhook_problem or operator_problem_of(
            exception=error,
            pipeline_run_id=run_metadata.pipeline_run_id,
            request_id=run_metadata.request_id,
        )
        if not reaches_error_trackers(status=problem_status_of(problem=problem), domain=problem.effective_domain):
            return
        report_exception(
            exception=error,
            kind=ErrorReportKind.RUN_FAILURE,
            problem=problem,
            pipeline_run_id=run_metadata.pipeline_run_id,
            request_id=run_metadata.request_id,
            pipe_code=pipe_job.pipe.code,
        )

    async def _run_bound(
        self,
        *,
        pipe_job: PipeJob,
        delivery_assignment: DeliveryAssignment | None,
    ) -> PipeOutput:
        pipeline_run_id: str = pipe_job.job_metadata.run_metadata.pipeline_run_id
        pipe_output: PipeOutput | None = None
        execution_error: Exception | None = None
        problem: PipelexProblem | None = None
        try:
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
                # Observe-and-reraise: records the failure so the run's tail sees it, then re-raises the original error below.
                execution_error = exc
                # The problem a FAILED webhook receives, the host's or a caller's, built only when a webhook is there to receive it.
                if delivery_assignment is not None and delivery_assignment.needs_run_problem:
                    problem = run_problem_of(
                        error=exc,
                        pipeline_run_id=pipeline_run_id,
                        request_id=pipe_job.job_metadata.run_metadata.request_id,
                    )
                # The error rides as identifiers and no traceback: the exception is re-raised below, and its traceback
                # belongs to whoever catches it, the CLI or the API's handler, which would otherwise print it twice. The
                # line carries the failure's code and the exception's class, never its text: the text can hold the
                # caller's own words, a function's message or a template's source, and a refused host, which no log line
                # carries, while the problem the caller receives holds them where the code declares them. The code is read
                # without building the problem, which a run with no webhook never builds.
                # `pipe_code` is the bare code `Pipe run starts` carries for the same pipe, so one query finds both lines.
                log.error(
                    "The execution of a pipe failed",
                    fields={
                        "pipe_code": pipe_job.pipe.code,
                        "pipe_ref": pipe_job.pipe.pipe_ref,
                        ERROR_CODE_FIELD: _failure_code(error=exc),
                        ERROR_TYPE_FIELD: type(exc).__name__,
                    },
                )
                # A security refusal also logs its security event, once, naming the run and never what it refused.
                emit_security_event_for_run(error=exc, run_metadata=pipe_job.job_metadata.run_metadata)
            finally:
                # When the run ended, which a caller's webhook event states, taken before the run's tail does its own work.
                finished_at = datetime.now(UTC)
                # Neither a result nor an exception: the run was cancelled or interrupted, which no `except Exception` catches.
                run_was_cancelled = execution_error is None and pipe_output is None
                try:
                    await self._finish_run(
                        pipe_job=pipe_job,
                        delivery_assignment=delivery_assignment,
                        pipe_output=pipe_output,
                        execution_error=execution_error,
                        problem=problem,
                        run_was_cancelled=run_was_cancelled,
                        finished_at=finished_at,
                        started_at=started_at,
                        input_kinds=input_kinds,
                        usage_tally=usage_tally,
                    )
                except Exception as tail_error:
                    if not run_was_cancelled:
                        # The run's failure is now the tail's, which replaces the pipe's own on its way to the caller and is
                        # the one the run's boundary reports.
                        raise
                    # A cancellation stays one, whatever its tail raised: the failure is logged by its class and code, never
                    # reported, since the run's outcome is its cancellation, which propagates once this block ends. As
                    # fields with no traceback, its text naming the run's data, a trace file or a webhook URL.
                    log.error(
                        "The run's tail failed after the run was cancelled",
                        fields=_secondary_failure_fields(exc=tail_error),
                    )
                except BaseException:
                    # Observe-and-reraise: an interruption, such as a cancellation, arrived during the run's tail and
                    # replaces the error the pipe failed with, which no `except Exception` sees any more. That error is the
                    # run's fault, so it is reported now, before the interruption propagates; the run sends no other report.
                    if execution_error is not None:
                        self._report_run_failure(error=execution_error, pipe_job=pipe_job, webhook_problem=problem)
                    raise

            if execution_error is not None:
                raise execution_error
        except Exception as escaping_error:
            # Observe-and-reraise at the run's boundary: the run fails with whatever escapes it, the pipe's own error or
            # one its tail raised after it, a tracer that would not close, a trace that would not assemble, statistics or
            # a delivery that failed, and that exception, the one the caller receives, is the one reported. A run sends
            # one report: a tail failure that replaced the pipe's own is reported in its place, never beside it. A
            # cancellation is no `Exception` and reports nothing, and no failure of a cancelled run's tail replaces it.
            self._report_run_failure(
                error=escaping_error,
                pipe_job=pipe_job,
                webhook_problem=problem if escaping_error is execution_error else None,
            )
            raise

        assert pipe_output is not None
        return pipe_output

    async def _finish_run(
        self,
        *,
        pipe_job: PipeJob,
        delivery_assignment: DeliveryAssignment | None,
        pipe_output: PipeOutput | None,
        execution_error: Exception | None,
        problem: PipelexProblem | None,
        run_was_cancelled: bool,
        finished_at: datetime,
        started_at: float,
        input_kinds: tuple[bool, bool],
        usage_tally: RunInferenceTally | None,
    ) -> None:
        """The run's tail, once the pipe executed, failed or was cancelled: close its trace, assemble it, count it, deliver it.

        A failure the tail expects, a trace that cannot be closed or a delivery that fails, after the pipe failed or the
        run was cancelled, is logged and the tail goes on, so the run keeps its own outcome. Any other failure escapes, and
        ``_run_bound`` decides what it means: the run's failure, or, for a cancelled run, a failure logged beside the
        cancellation.

        Args:
            pipe_job: The run's job.
            delivery_assignment: Where the run's results go, when anywhere.
            pipe_output: The run's output, when the pipe executed.
            execution_error: The error the pipe failed with, when it failed.
            problem: The problem built for the run's webhooks from that error, when they need one.
            run_was_cancelled: Whether the run ended with neither a result nor an error, cancelled or interrupted.
            finished_at: When the run ended, which a caller's webhook event states.
            started_at: When the run started, on the monotonic clock, for its statistics.
            input_kinds: Whether the run's inputs held an image, and whether they held a document.
            usage_tally: The run's inference calls, when its statistics are reported.
        """
        pipeline_run_id = pipe_job.job_metadata.run_metadata.pipeline_run_id
        closed_graph: GraphSpec | None = None
        tracer_manager = GraphTracerManager.get_instance()
        if tracer_manager is not None:
            try:
                closed_graph = tracer_manager.close_tracer(pipeline_run_id)
            except OSError as close_error:
                if execution_error is None and not run_was_cancelled:
                    # The run's failure is now this one, raised after the pipe executed, which the run's boundary reports.
                    raise
                # The run keeps its own failure, or its cancellation. A secondary failure rides as fields with no
                # traceback: the execution error is chained onto it, so its traceback would print the execution
                # error's text, which can quote the run's inputs. Its own text is not written either: an OSError's
                # names the file of the run's trace.
                log.error(
                    "The graph tracer could not be closed after the run failed or was cancelled",
                    fields=_secondary_failure_fields(exc=close_error),
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
            elif run_was_cancelled:
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

        if delivery_assignment is None:
            return
        status: DeliveryStatus
        delivered_problem = problem
        if execution_error is not None:
            status = DeliveryStatus.FAILED
        elif run_was_cancelled:
            # A cancelled run ended failed, so its webhooks are told so, as `run.cancelled`, and never that it
            # completed, while the cancellation itself propagates once the delivery is done.
            status = DeliveryStatus.FAILED
            if delivery_assignment.needs_run_problem:
                delivered_problem = _cancelled_run_problem(
                    pipeline_run_id=pipeline_run_id,
                    request_id=pipe_job.job_metadata.run_metadata.request_id,
                )
        else:
            status = DeliveryStatus.COMPLETED
        log.debug("Executing the delivery", fields={"delivery_status": status})
        try:
            await self._delivery_executor.execute(
                pipe_output=pipe_output,
                storage_scope=pipe_job.job_metadata.run_metadata.storage_scope,
                pipeline_run_id=pipeline_run_id,
                delivery_assignment=delivery_assignment,
                status=status,
                problem=delivered_problem,
                request_id=pipe_job.job_metadata.run_metadata.request_id,
                finished_at=finished_at,
                extras=pipe_job.job_metadata.run_metadata.extras,
            )
        except (DeliveryError, SsrfBlockedError) as delivery_error:
            # A caller's webhook never raises here: its failures are the delivery's own records. What can is
            # the storage, or one of the host's own webhooks, which the SSRF guard may refuse at fire time.
            if execution_error is None and not run_was_cancelled:
                # The run's failure is now the delivery's, the storage's or a host's webhook's after the pipe
                # executed, which the run's boundary reports as it reports the pipe's own.
                raise
            # The run keeps its own failure, or its cancellation. A refusal of the delivery's destination still logs its own security
            # event, naming the run, beside the one the run's failure logged if it was a refusal too.
            emit_security_event_for_run(error=delivery_error, run_metadata=pipe_job.job_metadata.run_metadata)
            # As fields with no traceback, for the same reason as the tracer's: the execution error is chained onto it.
            # By its code and class, never its text, which names the caller's webhook URL or the store it wrote to.
            log.error(
                "The delivery also failed after the pipe execution failed",
                fields=_secondary_failure_fields(exc=delivery_error),
            )

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
