from datetime import timedelta
from typing import Any, Callable, Coroutine, Generic, Protocol, TypeVar, Union, cast

from pydantic import BaseModel
from temporalio import workflow
from temporalio.client import Client as TemporalClient
from temporalio.client import WorkflowHandle
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError, ChildWorkflowError
from temporalio.workflow import ChildWorkflowHandle

from pipelex import log
from pipelex.config import get_config
from pipelex.temporal.exceptions import WorkflowExecutionError
from pipelex.temporal.temporal_manager import TemporalWorkerEnvironment, get_temporal_client, get_temporal_manager

T = TypeVar("T")
WorkflowOutput = TypeVar("WorkflowOutput", covariant=True)
WorkflowInput = TypeVar("WorkflowInput", bound=Union[BaseModel, dict[Any, Any]], contravariant=True)


class WorkflowCaller:
    def __init__(
        self,
        task_queue: str | None = None,
        workflow_execution_timeout: timedelta | None = None,
        run_timeout: timedelta | None = None,
        task_timeout: timedelta | None = None,
        retry_policy: RetryPolicy | None = None,
        start_delay: timedelta | None = None,
        rpc_timeout: timedelta | None = None,
    ):
        self.task_queue: str | None = task_queue
        self.execution_timeout: timedelta | None = workflow_execution_timeout
        self.run_timeout: timedelta | None = run_timeout
        self.task_timeout: timedelta | None = task_timeout
        self.retry_policy: RetryPolicy | None = retry_policy
        self.start_delay: timedelta | None = start_delay
        self.rpc_timeout: timedelta | None = rpc_timeout


class WorkflowClass(Protocol[WorkflowInput, WorkflowOutput]):
    @workflow.run
    async def run(self, workflow_arg: WorkflowInput) -> WorkflowOutput: ...


class WorkflowExecutor(WorkflowCaller, Generic[WorkflowInput, WorkflowOutput]):
    """A class that provides methods to execute and start workflows, both top-level and child workflows."""

    def __init__(
        self,
        temporal_client: TemporalClient | None = None,
        should_auto_connect_temporal: bool = False,
        worker_environment: TemporalWorkerEnvironment = TemporalWorkerEnvironment.EXTERNAL,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self._temporal_client = temporal_client
        self.should_auto_connect_temporal = should_auto_connect_temporal
        self.worker_environment = worker_environment

        log.dev(f"{self.__class__.__name__} initialized for task queue '{self.task_queue}'")
        log.dev(f"worker_environment='{self.worker_environment}', auto_connect_temporal={self.should_auto_connect_temporal}")

    @property
    def class_name(self) -> str:
        return self.__class__.__name__

    async def temporal_client(self) -> TemporalClient:
        """Get the temporal client, raising an error if not set."""
        if not get_config().temporal.is_enabled:
            msg = "Temporal is not enabled. Set temporal.is_enabled = true in pipelex.toml or use --temporal CLI flag."
            raise WorkflowExecutionError(msg)
        if self._temporal_client is None:
            if self.should_auto_connect_temporal:
                log.debug(f"{self.class_name} auto-connecting to Temporal server")
                self._temporal_client = await get_temporal_client(should_auto_connect=self.should_auto_connect_temporal)
            else:
                msg = "temporal_client is not connected and is not allowed to auto-connect"
                raise WorkflowExecutionError(msg)
        return self._temporal_client

    def make_workflow_id(self, base_id: str) -> str:
        workflow_id = get_temporal_manager().make_top_workflow_id(base_id=base_id)
        log.debug(f"Top workflow_id: {workflow_id}")
        return workflow_id

    async def execute_workflow(
        self,
        workflow_class: type[WorkflowClass[WorkflowInput, WorkflowOutput]],
        workflow_arg: WorkflowInput,
        workflow_id: str,
    ) -> WorkflowOutput:
        """Execute a workflow and wait for its completion."""
        try:
            client = await self.temporal_client()
            return await cast(
                "Callable[..., Coroutine[Any, Any, WorkflowOutput]]",
                client.execute_workflow,  # pyright: ignore[reportUnknownMemberType]
            )(
                workflow=workflow_class.run,
                arg=workflow_arg,
                id=workflow_id,
                task_queue=self.task_queue,
                execution_timeout=self.execution_timeout,
                retry_policy=self.retry_policy,
                run_timeout=self.run_timeout,
                task_timeout=self.task_timeout,
                start_delay=self.start_delay,
                rpc_timeout=self.rpc_timeout,
            )
        except Exception as exc:
            log.error(f"Failed to execute workflow {workflow_class.__name__}: {exc}")
            msg = f"Failed to execute workflow {workflow_class.__name__}"
            raise WorkflowExecutionError(msg) from exc

    async def start_workflow(
        self,
        workflow_class: type[WorkflowClass[WorkflowInput, WorkflowOutput]],
        workflow_arg: WorkflowInput,
        workflow_id: str,
    ) -> WorkflowHandle[WorkflowClass[WorkflowInput, WorkflowOutput], WorkflowOutput]:
        """Start a workflow without waiting for its completion."""
        try:
            client = await self.temporal_client()
            return await cast(
                "Callable[..., Coroutine[Any, Any, WorkflowHandle[WorkflowClass[WorkflowInput, WorkflowOutput], WorkflowOutput]]]",
                client.start_workflow,  # pyright: ignore[reportUnknownMemberType]
            )(
                workflow=workflow_class.run,
                arg=workflow_arg,
                id=workflow_id,
                task_queue=self.task_queue,
                execution_timeout=self.execution_timeout,
                retry_policy=self.retry_policy,
                run_timeout=self.run_timeout,
                task_timeout=self.task_timeout,
                start_delay=self.start_delay,
                rpc_timeout=self.rpc_timeout,
            )
        except Exception as exc:
            log.error(f"Failed to start workflow {workflow_class.__name__}: {exc}")
            msg = f"Failed to start workflow {workflow_class.__name__}"
            raise WorkflowExecutionError(msg) from exc

    async def execute_child_workflow(
        self,
        workflow_class: type[WorkflowClass[WorkflowInput, WorkflowOutput]],
        workflow_arg: WorkflowInput,
        workflow_id: str,
        child_task_queue: str | None = None,
    ) -> WorkflowOutput:
        """Execute a child workflow and wait for its completion."""
        try:
            return await cast(
                "Callable[..., Coroutine[Any, Any, WorkflowOutput]]",
                workflow.execute_child_workflow,  # pyright: ignore[reportUnknownMemberType]
            )(
                workflow=workflow_class.run,
                arg=workflow_arg,
                id=workflow_id,
                task_queue=child_task_queue,
                execution_timeout=self.execution_timeout,
                retry_policy=self.retry_policy,
                run_timeout=self.run_timeout,
                task_timeout=self.task_timeout,
            )
        except ChildWorkflowError as exc:
            log.error(f"ChildWorkflowError in {workflow_class.__name__} caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                msg = f"Application error in child workflow {workflow_class.__name__}"
                raise WorkflowExecutionError(msg) from exc.cause
            msg = f"Failed to execute child workflow {workflow_class.__name__}"
            raise WorkflowExecutionError(msg) from exc
        except Exception as exc:
            log.error(f"Failed to execute child workflow {workflow_class.__name__}: {exc}")
            msg = f"Failed to execute child workflow {workflow_class.__name__}"
            raise WorkflowExecutionError(msg) from exc

    async def start_child_workflow(
        self,
        workflow_class: type[WorkflowClass[WorkflowInput, WorkflowOutput]],
        workflow_arg: WorkflowInput,
        workflow_id: str,
        child_task_queue: str | None = None,
    ) -> ChildWorkflowHandle[WorkflowClass[WorkflowInput, WorkflowOutput], WorkflowOutput]:
        """Start a child workflow without waiting for its completion."""
        try:
            return await cast(
                "Callable[..., Coroutine[Any, Any, ChildWorkflowHandle[WorkflowClass[WorkflowInput, WorkflowOutput], WorkflowOutput]]]",
                workflow.start_child_workflow,  # pyright: ignore[reportUnknownMemberType]
            )(
                workflow=workflow_class.run,
                arg=workflow_arg,
                id=workflow_id,
                task_queue=child_task_queue,
                execution_timeout=self.execution_timeout,
                retry_policy=self.retry_policy,
                run_timeout=self.run_timeout,
                task_timeout=self.task_timeout,
            )
        except ChildWorkflowError as exc:
            log.error(f"ChildWorkflowError in {workflow_class.__name__} caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                msg = f"Application error in child workflow {workflow_class.__name__}"
                raise WorkflowExecutionError(msg) from exc.cause
            msg = f"Failed to start child workflow {workflow_class.__name__}"
            raise WorkflowExecutionError(msg) from exc
        except Exception as exc:
            log.error(f"Failed to start child workflow {workflow_class.__name__}: {exc}")
            msg = f"Failed to start child workflow {workflow_class.__name__}"
            raise WorkflowExecutionError(msg) from exc


class WorkflowExecutorFactory(Generic[WorkflowInput, WorkflowOutput]):
    @classmethod
    def create_executor(
        cls,
        task_queue: str | None = None,
        workflow_execution_timeout: timedelta | None = None,
        retry_policy: RetryPolicy | None = None,
        run_timeout: timedelta | None = None,
        task_timeout: timedelta | None = None,
        start_delay: timedelta | None = None,
        rpc_timeout: timedelta | None = None,
        temporal_client: TemporalClient | None = None,
        should_auto_connect_temporal: bool = False,
        worker_environment: TemporalWorkerEnvironment = TemporalWorkerEnvironment.EXTERNAL,
    ) -> WorkflowExecutor[WorkflowInput, WorkflowOutput]:
        """Creates a WorkflowExecutor with configuration from pipelex.temporal's config if not provided."""
        config = get_config().temporal.worker_config

        return WorkflowExecutor[WorkflowInput, WorkflowOutput](
            task_queue=task_queue or config.task_queue,
            workflow_execution_timeout=workflow_execution_timeout or config.workflow_execution_timeout,
            retry_policy=retry_policy or config.retry_policy,
            run_timeout=run_timeout or config.run_timeout,
            task_timeout=task_timeout or config.task_timeout,
            start_delay=start_delay or config.start_delay,
            rpc_timeout=rpc_timeout or config.rpc_timeout,
            temporal_client=temporal_client,
            should_auto_connect_temporal=should_auto_connect_temporal,
            worker_environment=worker_environment,
        )
