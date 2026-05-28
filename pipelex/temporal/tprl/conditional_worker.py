from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar, cast

import shortuuid

from pipelex import log
from pipelex.config import get_config
from pipelex.pipe_run.exceptions import AsyncExecutionNotEnabledError
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.temporal_manager import TemporalWorkerEnvironment
from pipelex.temporal.temporal_workflow_utils import is_in_temporal_workflow
from pipelex.temporal.tprl.workflow_caller import WorkflowExecutor, WorkflowInput, WorkflowOutput

FuncExecuteWorkflow = TypeVar("FuncExecuteWorkflow", bound=Callable[..., Awaitable[Any]])


def with_conditional_worker(execute_workflow: FuncExecuteWorkflow) -> FuncExecuteWorkflow:
    """Decorate a ``WorkflowExecutor`` dispatch method with the per-environment
    worker-bootstrap behaviour, gated by the deployment-level async-enabled
    guard.

    The guard fires here (before the ``match``) rather than inside the wrapped
    method body so it precedes the ``INTERNAL`` branch's ``temporal_client()``
    call: if the check ran inside the body it would be bypassed on the
    ``INTERNAL`` path, leaving only ``temporal_client()``'s lower-level check
    as the failsafe and silently inverting the facade docstring contract.

    The guard is skipped when the wrapped method is invoked from inside a
    Temporal workflow (the child-dispatch path through
    ``TemporalPipeRouter._run_pipe_job``): being inside a workflow proves the
    backend is already running, and ``get_config()`` is unsafe to read from
    the Temporal sandbox.
    """

    @wraps(execute_workflow)
    async def wrapper(
        self: WorkflowExecutor[WorkflowInput, WorkflowOutput],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        if not is_in_temporal_workflow() and not get_config().temporal.is_enabled:
            raise AsyncExecutionNotEnabledError.with_default_message()
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
