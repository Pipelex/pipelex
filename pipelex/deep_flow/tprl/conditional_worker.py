from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar, cast

import shortuuid
from deep_flow.deep_flow_hub import get_task_manager
from deep_flow.temporal_manager import TemporalWorkerEnvironment
from deep_flow.tprl.workflow_caller import WorkflowExecutor, WorkflowInput, WorkflowOutput

from pipelex import log

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
                self.task_queue = f"{self.task_queue}-{shortuuid.uuid()[:5]}"

                temporal_client = await self.temporal_client()
                async with get_task_manager().make_worker(
                    temporal_client=temporal_client,
                    task_queue=self.task_queue,
                    is_not_sandboxed=True,
                ):
                    return await execute_workflow(self, *args, **kwargs)
            case TemporalWorkerEnvironment.EXTERNAL:
                return await execute_workflow(self, *args, **kwargs)

    return cast("FuncExecuteWorkflow", wrapper)
