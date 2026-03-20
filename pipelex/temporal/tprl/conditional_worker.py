from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar, cast

import shortuuid

from pipelex import log
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.temporal_manager import TemporalWorkerEnvironment
from pipelex.temporal.tprl.workflow_caller import WorkflowExecutor, WorkflowInput, WorkflowOutput

FuncExecuteWorkflow = TypeVar("FuncExecuteWorkflow", bound=Callable[..., Awaitable[Any]])


def with_conditional_worker(execute_workflow: FuncExecuteWorkflow) -> FuncExecuteWorkflow:
    @wraps(execute_workflow)
    async def wrapper(
        self: WorkflowExecutor[WorkflowInput, WorkflowOutput],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        log.debug(f"worker_environment: {self.worker_environment}")
        match self.worker_environment:
            case TemporalWorkerEnvironment.INTERNAL:
                # add some random to task_queue to avoid this worker to take over other (possibly failed) tasks scheduled by preceding tests
                original_task_queue = self.task_queue
                self.task_queue = f"{self.task_queue}-{shortuuid.uuid()[:5]}"

                temporal_client = await self.temporal_client()
                try:
                    async with get_task_manager().make_worker(
                        temporal_client=temporal_client,
                        task_queue=self.task_queue,
                        is_not_sandboxed=True,
                    ):
                        return await execute_workflow(self, *args, **kwargs)
                finally:
                    self.task_queue = original_task_queue
            case TemporalWorkerEnvironment.EXTERNAL:
                return await execute_workflow(self, *args, **kwargs)

    return cast("FuncExecuteWorkflow", wrapper)
