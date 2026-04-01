from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from typing_extensions import override

with workflow.unsafe.imports_passed_through():
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.pipe_run.delivery_assignment import DeliveryStatus
    from pipelex.temporal.log_temporal import workflow_log
    from pipelex.temporal.tprl.workflow_caller import WorkflowClass
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
        workflow_log.debug("WfPipeRun start")

        pipe_job = workflow_arg.pipe_job
        delivery_assignment = workflow_arg.delivery_assignment
        pipeline_run_id: str = pipe_job.job_metadata.pipeline_run_id

        # Step 1: Execute the pipe via child workflow
        workflow_log.debug(f"Starting child WfPipeRouter for pipe '{pipe_job.pipe.code}'")
        status: DeliveryStatus = DeliveryStatus.COMPLETED
        pipe_output: PipeOutput | None = None
        execution_error: Exception | None = None

        try:
            pipe_output = await workflow.execute_child_workflow(
                WfPipeRouter.run,
                arg=pipe_job,
                id=f"{workflow.info().workflow_id}-pipe-router",
            )
            workflow_log.debug("WfPipeRouter completed successfully")
        except Exception as exc:
            status = DeliveryStatus.FAILED
            execution_error = exc
            workflow_log.error(f"WfPipeRouter failed: {exc}")

        # Step 2: Run delivery activity (always — to notify completion Lambda of success or failure)
        if delivery_assignment is not None:
            workflow_log.debug(f"Running delivery: pipeline_run_id={pipeline_run_id}, status={status}")
            activity_arg = DeliveryActivityArg(
                pipeline_run_id=pipeline_run_id,
                delivery_assignment=delivery_assignment,
                status=status,
            )
            # Include pipe_output only on success
            if pipe_output is not None:
                activity_arg = activity_arg.model_copy(update={"pipe_output": pipe_output})

            await workflow.execute_activity(
                act_deliver,
                arg=activity_arg,
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            workflow_log.debug("Delivery completed")

        # Re-raise the execution error after delivery so the workflow is marked as failed
        if execution_error is not None:
            raise execution_error

        assert pipe_output is not None
        workflow_log.debug("WfPipeRun complete")
        return pipe_output
