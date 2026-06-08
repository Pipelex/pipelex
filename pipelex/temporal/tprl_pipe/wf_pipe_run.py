from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ChildWorkflowError
from typing_extensions import override

with workflow.unsafe.imports_passed_through():
    from pipelex.base_exceptions import ErrorReport  # noqa: TC001  # must traverse the workflow sandbox
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.pipe_run.delivery_assignment import DeliveryStatus
    from pipelex.runtime_bridge.primitives.pipe_run_arg import PipeRunArg
    from pipelex.temporal.exceptions import WorkflowExecutionError
    from pipelex.temporal.log_temporal import WorkflowLog
    from pipelex.temporal.tprl.observability import build_search_attributes, build_static_summary
    from pipelex.temporal.tprl.temporal_error import recover_error_report
    from pipelex.temporal.tprl.workflow_caller import WorkflowClass
    from pipelex.temporal.tprl_pipe.act_assemble_tracing import AssembleTracingArg, act_assemble_tracing
    from pipelex.temporal.tprl_pipe.act_deliver import DeliveryActivityArg, act_deliver
    from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter


@workflow.defn(name="wf_pipe_run")
class WfPipeRun(WorkflowClass[PipeRunArg, PipeOutput]):
    """Parent workflow that orchestrates pipe execution + delivery.

    1. Runs WfPipeRouter as a child workflow to execute the pipe
    2. Runs a delivery activity — always runs, even on failure (to notify the completion Lambda)
    """

    @override
    @workflow.run
    async def run(self, workflow_arg: PipeRunArg) -> PipeOutput:
        pipe_job = workflow_arg.pipe_job
        # Bound once per invocation: every record below carries this run's
        # request_id (None when the run carries no inbound API request id).
        workflow_log = WorkflowLog(request_id=pipe_job.job_metadata.request_id)
        workflow_log.debug("WfPipeRun start")

        delivery_assignment = workflow_arg.delivery_assignment
        pipeline_run_id: str = pipe_job.job_metadata.pipeline_run_id

        # Step 1: Execute the pipe via child workflow
        workflow_log.debug(f"Starting child WfPipeRouter for pipe '{pipe_job.pipe.code}'")
        status: DeliveryStatus = DeliveryStatus.COMPLETED
        pipe_output: PipeOutput | None = None
        execution_error: WorkflowExecutionError | None = None
        error_report: ErrorReport | None = None

        # The wf_pipe_router child runs the same pipe as wf_pipe_run, so its
        # search attributes and static summary are identical — re-derive them
        # from the same pipe_job. Dispatched via ``workflow.execute_child_workflow``
        # directly so the recorded ``StartChildWorkflowExecution`` command is a
        # pure function of the workflow input: no config-derived
        # execution_timeout / retry_policy / task_queue smuggled in via the
        # ``WorkflowExecutorFactory``, which would change across deploys and
        # break determinism on replay after a config edit.
        try:
            pipe_output = await workflow.execute_child_workflow(
                WfPipeRouter.run,
                arg=pipe_job,
                id=f"{workflow.info().workflow_id}_pipe-router",
                search_attributes=build_search_attributes(pipe_job),
                static_summary=build_static_summary(pipe_job.pipe),
            )
            workflow_log.debug("WfPipeRouter completed successfully")
        except ChildWorkflowError as exc:
            status = DeliveryStatus.FAILED
            # Wrap the raw ``ChildWorkflowError`` as ``WorkflowExecutionError`` so the rest of
            # this function and the outer ``execute_workflow`` caller continue to see the same
            # Pipelex error type as before — the integration test ``test_wf_pipe_run_failure_path``
            # pins the workflow_failure_exception_types contract on ``WorkflowExecutionError``.
            # ``recover_error_report`` lifts the structured classification out of the child failure
            # (``ChildWorkflowError`` exposes it via ``exc.cause``) so the FAILED webhook carries it.
            #
            # Manual ``__cause__`` wire (not ``raise X from exc``): we hold the wrapped error for a
            # deferred re-raise in the post-delivery block below so ``act_deliver`` still fires on
            # the failure path. Raising here would short-circuit delivery.
            error_report = recover_error_report(exc.cause if exc.cause is not None else exc)
            execution_error = WorkflowExecutionError("WfPipeRouter failed", error_report=error_report)
            execution_error.__cause__ = exc
            workflow_log.error(f"WfPipeRouter failed: {exc}")

        # Step 2: Assemble full graph + usage from trace events (cross-worker)
        # Runs as an activity because DynamoDB reads are I/O forbidden in workflows. The dispatch is
        # gated on the run's emit flags (F1): a costs-only run assembles usage but no graph, so
        # graph_spec stays None — matching DIRECT mode and preserving the --no-graph contract.
        trace_context = pipe_job.job_metadata.trace_context
        if pipe_output is not None and trace_context is not None and (trace_context.emit_graph_events or trace_context.emit_usage_events):
            try:
                tracing_assembly = await workflow.execute_activity(
                    act_assemble_tracing,
                    arg=AssembleTracingArg(
                        pipeline_run_id=pipeline_run_id,
                        domain_code=pipe_job.pipe.domain_code,
                        main_pipe_code=pipe_job.pipe.code,
                        assemble_graph=trace_context.emit_graph_events,
                        assemble_usage=trace_context.emit_usage_events,
                    ),
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
                # Mirror DIRECT's assemble_tracing_on_output: copy every populated field, including the
                # best-effort *_assembly_error fields. assemble_tracing catches the expected read/assemble
                # failures internally and returns them on these fields (no exception raised), so without
                # this the failure would be observable in DIRECT but silently lost in TEMPORAL.
                if tracing_assembly.graph_spec is not None:
                    pipe_output.graph_spec = tracing_assembly.graph_spec
                if tracing_assembly.graph_assembly_error is not None:
                    pipe_output.graph_assembly_error = tracing_assembly.graph_assembly_error
                if tracing_assembly.tokens_usages is not None:
                    pipe_output.tokens_usages = tracing_assembly.tokens_usages
                if tracing_assembly.usage_assembly_error is not None:
                    pipe_output.usage_assembly_error = tracing_assembly.usage_assembly_error
            except ActivityError as assembly_exc:
                workflow_log.warning(f"Tracing assembly failed, continuing with delivery: {assembly_exc}")
                # Record the failure only on the concern(s) actually requested, so a costs-only run never
                # surfaces a graph_assembly_error (and vice versa).
                if trace_context.emit_graph_events:
                    pipe_output.graph_assembly_error = str(assembly_exc)
                if trace_context.emit_usage_events:
                    pipe_output.usage_assembly_error = str(assembly_exc)

        # Step 3: Run delivery activity if requested — notifies the completion
        # Lambda of success or failure when a delivery_assignment was provided.
        # No assignment → no delivery (matches PipeRun direct-mode semantics).
        delivery_error: ActivityError | None = None
        if delivery_assignment is not None:
            workflow_log.debug(f"Running delivery: pipeline_run_id={pipeline_run_id}, status={status}")
            activity_arg = DeliveryActivityArg(
                user_id=pipe_job.job_metadata.user_id,
                pipeline_run_id=pipeline_run_id,
                delivery_assignment=delivery_assignment,
                status=status,
                error_report=error_report,
                request_id=pipe_job.job_metadata.request_id,
            )
            # Include pipe_output only on success
            if pipe_output is not None:
                activity_arg = activity_arg.model_copy(update={"pipe_output": pipe_output})

            try:
                await workflow.execute_activity(
                    act_deliver,
                    arg=activity_arg,
                    start_to_close_timeout=timedelta(seconds=60),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
                workflow_log.debug("Delivery completed")
            except ActivityError as activity_error:
                # Capture but do not raise yet: when both router and delivery fail
                # (e.g., pipe failure + webhook outage) we must preserve the original
                # execution_error for failure attribution, matching direct-mode PipeRun.
                delivery_error = activity_error
                workflow_log.error(f"Delivery activity failed: {activity_error}")

        # Re-raise: prefer the original execution error so failure attribution stays
        # correct when delivery also fails. Fall back to the delivery error otherwise.
        if execution_error is not None:
            raise execution_error
        if delivery_error is not None:
            raise delivery_error

        assert pipe_output is not None
        workflow_log.debug("WfPipeRun complete")
        return pipe_output
