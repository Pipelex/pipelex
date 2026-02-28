from typing import cast

from typing_extensions import override

from pipelex import log
from pipelex.config import get_config
from pipelex.core.pipe_output import PipeOutput, PipeOutputType
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.working_memory import WorkingMemory
from pipelex.deep_flow.tprl.workflow_caller import WorkflowExecutor, WorkflowExecutorFactory
from pipelex.deep_flow.tprl_pipe.wf_pipe_router import WfPipeRouter
from pipelex.hub import get_required_pipe
from pipelex.pipe_works.pipe_job import PipeJob
from pipelex.pipe_works.pipe_job_factory import PipeJobFactory
from pipelex.pipe_works.pipe_router_protocol import PipeRouterProtocol
from pipelex.pipeline.job_metadata import JobMetadata


class PipeRouterChild(WorkflowExecutor[PipeJob, PipeOutput], PipeRouterProtocol):
    @override
    async def run_pipe_job(
        self,
        pipe_job: PipeJob,
        wfid: str | None = None,
    ) -> PipeOutputType:  # pyright: ignore[reportInvalidTypeVarUse]
        log.debug("PipeRouterChild run_pipe_job within workflow")
        executor = WorkflowExecutorFactory[PipeJob, PipeOutput]().create_executor(task_queue=None)
        pipe_output = await executor.execute_child_workflow(
            workflow_class=WfPipeRouter,
            workflow_id=executor.make_workflow_id(base_id=wfid or "run-pipe-router"),
            workflow_arg=pipe_job,
        )
        return cast("PipeOutputType", pipe_output)

    @override
    async def run_pipe_code(
        self,
        pipe_code: str,
        pipe_run_params: PipeRunParams | None = None,
        job_metadata: JobMetadata | None = None,
        working_memory: WorkingMemory | None = None,
        output_name: str | None = None,
        wfid: str | None = None,
    ) -> PipeOutputType:  # pyright: ignore[reportInvalidTypeVarUse]
        pipe = get_required_pipe(pipe_code)
        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            pipe_run_params=pipe_run_params,
            job_metadata=job_metadata,
            working_memory=working_memory,
            output_name=output_name,
        )
        pipe_output: PipeOutputType = await self.run_pipe_job(
            pipe_job=pipe_job,
            wfid=wfid,
        )
        return pipe_output


def make_tprl_pipe_router_child() -> PipeRouterChild:
    worker_config = get_config().deep_flow.worker_config
    return PipeRouterChild(
        workflow_execution_timeout=worker_config.workflow_execution_timeout,
        retry_policy=worker_config.retry_policy,
    )
