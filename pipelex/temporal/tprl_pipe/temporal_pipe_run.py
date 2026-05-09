from datetime import timedelta

from temporalio.client import WorkflowHandle
from temporalio.common import RetryPolicy
from typing_extensions import override

from pipelex import log
from pipelex.config import get_config
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_protocol import PipeRunProtocol
from pipelex.runtime_bridge.primitives.pipe_run_arg import PipeRunArg
from pipelex.runtime_bridge.primitives.submitter_hydration import rehydrate_pipe_output_with_crate
from pipelex.temporal.temporal_manager import TemporalWorkerEnvironment
from pipelex.temporal.tprl.conditional_worker import with_conditional_worker
from pipelex.temporal.tprl.workflow_caller import WorkflowClass, WorkflowExecutor, WorkflowExecutorFactory
from pipelex.temporal.tprl_pipe.wf_pipe_run import WfPipeRun


class TemporalPipeRun(WorkflowExecutor[PipeRunArg, PipeOutput], PipeRunProtocol):
    """Temporal-mode PipeRun: dispatches WfPipeRun workflow which orchestrates execution + delivery."""

    def __init__(
        self,
        task_queue: str,
        workflow_execution_timeout: timedelta | None = None,
        retry_policy: RetryPolicy | None = None,
        should_auto_connect_temporal: bool = False,
        worker_environment: TemporalWorkerEnvironment = TemporalWorkerEnvironment.EXTERNAL,
    ) -> None:
        log.debug(f"TemporalPipeRun init with worker_environment: {worker_environment}")
        super().__init__(
            workflow_execution_timeout=workflow_execution_timeout,
            retry_policy=retry_policy,
            task_queue=task_queue,
            should_auto_connect_temporal=should_auto_connect_temporal,
            worker_environment=worker_environment,
        )

    @override
    @with_conditional_worker
    async def run(
        self,
        pipe_job: PipeJob,
        delivery_assignment: DeliveryAssignment | None = None,
        wfid: str | None = None,
    ) -> PipeOutput:
        """Execute a pipe run via Temporal (blocking — waits for completion)."""
        pipe_run_arg = PipeRunArg(
            pipe_job=pipe_job,
            delivery_assignment=delivery_assignment,
        )
        pipe_run_arg = pipe_run_arg.prepare_for_temporal()

        executor = WorkflowExecutorFactory[PipeRunArg, PipeOutput]().create_executor(
            task_queue=self.task_queue,
            should_auto_connect_temporal=self.should_auto_connect_temporal,
            worker_environment=self.worker_environment,
        )
        pipe_output = await executor.execute_workflow(
            workflow_class=WfPipeRun,
            workflow_id=self.make_workflow_id(base_id=wfid or self.class_name),
            workflow_arg=pipe_run_arg,
        )

        # Rehydrate PipeOutput on the submitter. When the pipe_job carries a crate,
        # the helper opens a per-call scoped library so the submitter does not need
        # the bundle pre-loaded in its global registry.
        return rehydrate_pipe_output_with_crate(pipe_output, pipe_job.library_crate)

    @with_conditional_worker
    async def start(
        self,
        pipe_job: PipeJob,
        delivery_assignment: DeliveryAssignment | None = None,
        wfid: str | None = None,
    ) -> tuple[str, WorkflowHandle[WorkflowClass[PipeRunArg, PipeOutput], PipeOutput]]:
        """Start a pipe run without waiting for completion.

        Returns the workflow_id and a WorkflowHandle that can be awaited later.
        """
        log.debug(f"TemporalPipeRun start using task_queue: {self.task_queue}")
        pipe_run_arg = PipeRunArg(
            pipe_job=pipe_job,
            delivery_assignment=delivery_assignment,
        )
        pipe_run_arg = pipe_run_arg.prepare_for_temporal()

        executor = WorkflowExecutorFactory[PipeRunArg, PipeOutput]().create_executor(
            task_queue=self.task_queue,
            should_auto_connect_temporal=self.should_auto_connect_temporal,
            worker_environment=self.worker_environment,
        )
        workflow_id = self.make_workflow_id(base_id=wfid or self.class_name)
        handle = await executor.start_workflow(
            workflow_class=WfPipeRun,
            workflow_id=workflow_id,
            workflow_arg=pipe_run_arg,
        )
        return workflow_id, handle


def make_temporal_pipe_run(
    task_queue: str | None = None,
    workflow_execution_timeout: timedelta | None = None,
    retry_policy: RetryPolicy | None = None,
    should_auto_connect_temporal: bool = True,
    worker_environment: TemporalWorkerEnvironment = TemporalWorkerEnvironment.EXTERNAL,
) -> TemporalPipeRun:
    """Factory: creates a TemporalPipeRun from config defaults."""
    worker_config = get_config().temporal.worker_config
    return TemporalPipeRun(
        task_queue=task_queue or worker_config.task_queue,
        workflow_execution_timeout=workflow_execution_timeout or worker_config.workflow_execution_timeout,
        retry_policy=retry_policy or worker_config.retry_policy,
        should_auto_connect_temporal=should_auto_connect_temporal,
        worker_environment=worker_environment,
    )
