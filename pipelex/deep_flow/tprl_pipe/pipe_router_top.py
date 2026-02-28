from datetime import timedelta
from typing import cast

from citadel.config_citadel import get_config
from deep_flow.temporal_manager import TemporalWorkerEnvironment
from deep_flow.tprl.conditional_worker import with_conditional_worker
from deep_flow.tprl.workflow_caller import WorkflowExecutor, WorkflowExecutorFactory
from deep_flow.tprl_pipe.wf_pipe_router import WfPipeRouter
from temporalio.common import RetryPolicy
from typing_extensions import override

from pipelex import log
from pipelex.core.pipe_output import PipeOutput, PipeOutputType
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.working_memory import WorkingMemory
from pipelex.hub import get_required_pipe
from pipelex.pipe_works.pipe_job import PipeJob
from pipelex.pipe_works.pipe_job_factory import PipeJobFactory
from pipelex.pipe_works.pipe_router_protocol import PipeRouterProtocol
from pipelex.pipeline.job_metadata import JobMetadata


class PipeRouterTop(WorkflowExecutor[PipeJob, PipeOutput], PipeRouterProtocol):
    def __init__(
        self,
        task_queue: str,
        workflow_execution_timeout: timedelta | None = None,
        retry_policy: RetryPolicy | None = None,
        should_auto_connect_temporal: bool = False,
        worker_environment: TemporalWorkerEnvironment = TemporalWorkerEnvironment.EXTERNAL,
    ):
        log.debug(f"PipeRouterTop init with worker_environment: {worker_environment}")
        super().__init__(
            workflow_execution_timeout=workflow_execution_timeout,
            retry_policy=retry_policy,
            task_queue=task_queue,
            should_auto_connect_temporal=should_auto_connect_temporal,
            worker_environment=worker_environment,
        )
        self.task_queue = task_queue

    @override
    @with_conditional_worker
    async def run_pipe_job(
        self,
        pipe_job: PipeJob,
        wfid: str | None = None,
    ) -> PipeOutputType:  # pyright: ignore[reportInvalidTypeVarUse]
        log.debug(f"PipeRouterTop run_pipe_job using task_queue: {self.task_queue} with worker_environment={self.worker_environment}")
        executor = WorkflowExecutorFactory[PipeJob, PipeOutput]().create_executor(
            task_queue=self.task_queue,
            should_auto_connect_temporal=self.should_auto_connect_temporal,
            worker_environment=self.worker_environment,
        )
        pipe_output = await executor.execute_workflow(
            workflow_class=WfPipeRouter,
            workflow_id=self.make_workflow_id(base_id=wfid or self.class_name),
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
            job_metadata=job_metadata,
            working_memory=working_memory,
            output_name=output_name,
            pipe_run_params=pipe_run_params,
        )
        pipe_output: PipeOutputType = await self.run_pipe_job(
            pipe_job=pipe_job,
            wfid=wfid,
        )
        return pipe_output


def make_tprl_pipe_router_top(
    task_queue: str | None = None,
    workflow_execution_timeout: timedelta | None = None,
    retry_policy: RetryPolicy | None = None,
    should_auto_connect_temporal: bool = True,
    worker_environment: TemporalWorkerEnvironment = TemporalWorkerEnvironment.EXTERNAL,
) -> PipeRouterTop:
    """This factory is only passing your settings or using defaults from deep_flow's config."""
    worker_config = get_config().deep_flow.worker_config
    return PipeRouterTop(
        task_queue=task_queue or worker_config.task_queue,
        workflow_execution_timeout=workflow_execution_timeout or worker_config.workflow_execution_timeout,
        retry_policy=retry_policy or worker_config.retry_policy,
        should_auto_connect_temporal=should_auto_connect_temporal,
        worker_environment=worker_environment,
    )
