from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from typing_extensions import override

from pipelex import log
from pipelex.config import get_config
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.observer.observer_protocol import ObserverNoOp
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_router_protocol import PipeRouterProtocol
from pipelex.temporal.temporal_manager import TemporalWorkerEnvironment
from pipelex.temporal.temporal_workflow_utils import is_in_temporal_workflow
from pipelex.temporal.tprl.conditional_worker import with_conditional_worker
from pipelex.temporal.tprl.observability import (
    build_search_attributes,
    build_static_details,
    build_static_summary,
)
from pipelex.temporal.tprl.workflow_caller import WorkflowExecutor, WorkflowExecutorFactory
from pipelex.temporal.tprl_pipe.submitter_hydration import rehydrate_pipe_output_with_crate
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter


class TemporalPipeRouter(WorkflowExecutor[PipeJob, PipeOutput], PipeRouterProtocol):
    """Temporal pipe router: auto-detects whether to dispatch as top-level or child workflow.

    When called outside a Temporal workflow, dispatches via execute_workflow (top-level).
    When called inside a Temporal workflow, dispatches via execute_child_workflow (child).
    """

    def __init__(
        self,
        task_queue: str,
        workflow_execution_timeout: timedelta | None = None,
        retry_policy: RetryPolicy | None = None,
        should_auto_connect_temporal: bool = False,
        worker_environment: TemporalWorkerEnvironment = TemporalWorkerEnvironment.EXTERNAL,
    ):
        log.debug(f"TemporalPipeRouter init with worker_environment: {worker_environment}")
        super().__init__(
            workflow_execution_timeout=workflow_execution_timeout,
            retry_policy=retry_policy,
            task_queue=task_queue,
            should_auto_connect_temporal=should_auto_connect_temporal,
            worker_environment=worker_environment,
        )
        self.observer = ObserverNoOp()

    @override
    @with_conditional_worker
    async def _run_pipe_job(
        self,
        pipe_job: PipeJob,
    ) -> PipeOutput:
        pipe_job = pipe_job.prepare_for_temporal()

        if is_in_temporal_workflow():
            # Child workflow dispatch (inside a Temporal workflow).
            # The child id is a slash-separated path off the parent's workflow id,
            # with a pipe-code prefix for readability and an 8-hex-char disambiguator
            # from ``workflow.uuid4()`` (replay-safe — Temporal's uuid4 is deterministic).
            log.debug("TemporalPipeRouter: child workflow dispatch")
            parent_workflow_id = workflow.info().workflow_id
            child_workflow_id = f"{parent_workflow_id}/{pipe_job.pipe.code}-{str(workflow.uuid4())[:8]}"
            executor = WorkflowExecutorFactory[PipeJob, PipeOutput]().create_executor(task_queue=None)
            pipe_output = await executor.execute_child_workflow(
                workflow_class=WfPipeRouter,
                workflow_id=child_workflow_id,
                workflow_arg=pipe_job,
                search_attributes=dict(build_search_attributes(pipe_job)),
                static_summary=build_static_summary(pipe_job.pipe),
            )
        else:
            # Top-level dispatch (outside a Temporal workflow)
            log.debug(f"TemporalPipeRouter: top-level dispatch, task_queue={self.task_queue}")
            executor = WorkflowExecutorFactory[PipeJob, PipeOutput]().create_executor(
                task_queue=self.task_queue,
                workflow_execution_timeout=self.execution_timeout,
                retry_policy=self.retry_policy,
                run_timeout=self.run_timeout,
                task_timeout=self.task_timeout,
                start_delay=self.start_delay,
                rpc_timeout=self.rpc_timeout,
                should_auto_connect_temporal=self.should_auto_connect_temporal,
                worker_environment=self.worker_environment,
            )
            pipe_output = await executor.execute_workflow(
                workflow_class=WfPipeRouter,
                workflow_id=self.make_workflow_id(pipeline_run_id=pipe_job.job_metadata.pipeline_run_id),
                workflow_arg=pipe_job,
                search_attributes=dict(build_search_attributes(pipe_job)),
                static_summary=build_static_summary(pipe_job.pipe),
                static_details=build_static_details(pipe_job),
            )

        # Rehydrate PipeOutput: reconstruct typed WorkingMemory from raw dict.
        # Uses a per-call scoped library when the pipe_job carries a crate so the
        # submitter does not need to have pre-loaded the bundle into its global registry.
        return rehydrate_pipe_output_with_crate(pipe_output, pipe_job.library_crate)


def make_temporal_pipe_router(
    task_queue: str | None = None,
    workflow_execution_timeout: timedelta | None = None,
    retry_policy: RetryPolicy | None = None,
    should_auto_connect_temporal: bool = True,
    worker_environment: TemporalWorkerEnvironment = TemporalWorkerEnvironment.EXTERNAL,
) -> TemporalPipeRouter:
    """Factory: creates a TemporalPipeRouter from config defaults."""
    worker_config = get_config().temporal.worker_config
    return TemporalPipeRouter(
        task_queue=task_queue or worker_config.default_task_queue,
        workflow_execution_timeout=workflow_execution_timeout or worker_config.workflow_execution_timeout,
        retry_policy=retry_policy or worker_config.retry_policy,
        should_auto_connect_temporal=should_auto_connect_temporal,
        worker_environment=worker_environment,
    )
