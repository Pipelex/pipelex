from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ChildWorkflowError
from typing_extensions import override

with workflow.unsafe.imports_passed_through():
    from pipelex.base_exceptions import ErrorReport  # noqa: TC001  # must traverse the workflow sandbox
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.pipe_run.delivery_assignment import DeliveryStatus
    from pipelex.temporal.exceptions import WorkflowExecutionError
    from pipelex.temporal.log_temporal import WorkflowLog
    from pipelex.temporal.tprl.observability import build_search_attributes, build_static_summary
    from pipelex.temporal.tprl.temporal_error import recover_error_report
    from pipelex.temporal.tprl.workflow_caller import WorkflowClass
    from pipelex.temporal.tprl_pipe.act_assemble_graph import AssembleGraphArg, act_assemble_graph
    from pipelex.temporal.tprl_pipe.act_deliver import DeliveryActivityArg, act_deliver
    from pipelex.temporal.tprl_pipe.pipe_run_arg import PipeRunArg
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
                id=f"{workflow.info().workflow_id}/pipe-router",
                search_attributes=build_search_attributes(pipe_job),
                static_summary=build_static_summary(pipe_job.pipe),
            )
            workflow_log.debug("WfPipeRouter completed successfully")
        except ChildWorkflowError as exc:
            status = DeliveryStatus.FAILED
            # Hold the wrapped error for a deferred re-raise after delivery — raising here would short-circuit ``act_deliver``.
            # ``ChildWorkflowError`` exposes the underlying failure via ``exc.cause``, not ``__cause__``.
            error_report = recover_error_report(exc.cause if exc.cause is not None else exc)
            execution_error = WorkflowExecutionError("WfPipeRouter failed", error_report=error_report)
            execution_error.__cause__ = exc
            workflow_log.error(f"WfPipeRouter failed: {exc}")

        # Step 2: Assemble full graph from trace events (cross-worker)
        # Runs as an activity because DynamoDB reads are I/O forbidden in workflows.
        if pipe_output is not None:
            try:
                graph_spec = await workflow.execute_activity(
                    act_assemble_graph,
                    arg=AssembleGraphArg(
                        pipeline_run_id=pipeline_run_id,
                        domain_code=pipe_job.pipe.domain_code,
                        main_pipe_code=pipe_job.pipe.code,
                    ),
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
                if graph_spec is not None:
                    pipe_output.graph_spec = graph_spec
            except ActivityError as graph_exc:
                workflow_log.warning(f"Graph assembly failed, continuing with delivery: {graph_exc}")
                pipe_output.graph_assembly_error = str(graph_exc)

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
