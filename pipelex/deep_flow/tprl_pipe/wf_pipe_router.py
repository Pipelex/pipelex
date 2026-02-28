from temporalio import workflow
from temporalio.exceptions import ActivityError, ApplicationError
from typing_extensions import override

from pipelex import log
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.pipe_job import PipeJob

with workflow.unsafe.imports_passed_through():
    from temporalio import workflow

    from pipelex import log
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.deep_flow.log_temporal import workflow_log
    from pipelex.deep_flow.tprl.temporal_error import TemporalError
    from pipelex.deep_flow.tprl.workflow_caller import WorkflowClass
    from pipelex.pipe_run.pipe_job import PipeJob


@workflow.defn(name="wf_pipe_router")
class WfPipeRouter(WorkflowClass[PipeJob, PipeOutput]):
    @override
    @workflow.run
    async def run(
        self,
        workflow_arg: PipeJob,
    ) -> PipeOutput:
        workflow_log.debug("Workflow start")
        working_memory = workflow_arg.working_memory

        pipe = workflow_arg.pipe
        log.verbose(f"Routing {pipe.__class__.__name__} pipe '{workflow_arg.pipe.code}': {pipe.definition}")

        try:
            pipe_output = await pipe.run_pipe(
                job_metadata=workflow_arg.job_metadata,
                working_memory=working_memory,
                output_name=workflow_arg.output_name,
                pipe_run_params=workflow_arg.pipe_run_params,
            )
        except ActivityError as exc:
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise

        workflow_log.debug("Workflow complete")
        return pipe_output
