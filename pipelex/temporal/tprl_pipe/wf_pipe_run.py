from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from typing_extensions import override

with workflow.unsafe.imports_passed_through():
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.temporal.log_temporal import workflow_log
    from pipelex.temporal.tprl.workflow_caller import WorkflowClass
    from pipelex.temporal.tprl_pipe.act_deliver import DeliveryActivityArg, act_deliver
    from pipelex.temporal.tprl_pipe.pipe_run_arg import PipeRunArg
    from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter


@workflow.defn(name="wf_pipe_run")
class WfPipeRun(WorkflowClass[PipeRunArg, PipeOutput]):
    """Parent workflow that orchestrates pipe execution + delivery.

    1. Runs WfPipeRouter as a child workflow to execute the pipe
    2. Runs a delivery activity (storage + webhooks) if a delivery assignment is provided
    """

    @override
    @workflow.run
    async def run(self, workflow_arg: PipeRunArg) -> PipeOutput:
        workflow_log.debug("WfPipeRun start")

        pipe_job = workflow_arg.pipe_job
        delivery_assignment = workflow_arg.delivery_assignment

        # Step 1: Execute the pipe via child workflow (existing WfPipeRouter, unchanged)
        workflow_log.debug(f"Starting child WfPipeRouter for pipe '{pipe_job.pipe.code}'")
        pipe_output: PipeOutput = await workflow.execute_child_workflow(
            WfPipeRouter.run,
            arg=pipe_job,
            id=f"{workflow.info().workflow_id}-pipe-router",
        )
        workflow_log.debug("WfPipeRouter completed")

        # Step 2: Run delivery activity (storage first, then webhooks)
        if delivery_assignment is not None:
            pipeline_run_id: str = pipe_job.job_metadata.pipeline_run_id
            workflow_log.debug(f"Running delivery for pipeline_run_id={pipeline_run_id}")
            await workflow.execute_activity(
                act_deliver,
                arg=DeliveryActivityArg(
                    pipe_output=pipe_output,
                    pipeline_run_id=pipeline_run_id,
                    delivery_assignment=delivery_assignment,
                ),
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            workflow_log.debug("Delivery completed")

        workflow_log.debug("WfPipeRun complete")
        return pipe_output
