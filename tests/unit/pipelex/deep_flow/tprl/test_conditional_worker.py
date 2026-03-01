from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.deep_flow.temporal_manager import TemporalWorkerEnvironment
from pipelex.deep_flow.tprl.conditional_worker import with_conditional_worker
from pipelex.deep_flow.tprl.workflow_caller import WorkflowExecutor


@pytest.mark.asyncio(loop_scope="class")
class TestConditionalWorker:
    """Verify that with_conditional_worker restores task_queue after execution."""

    async def test_task_queue_not_mutated_after_multiple_calls(self, mocker: MockerFixture) -> None:
        """Calling a decorated method multiple times must not grow the task_queue name."""
        original_queue = "my-task-queue"

        # Build a concrete WorkflowExecutor with INTERNAL worker environment
        executor: WorkflowExecutor[Any, Any] = WorkflowExecutor(
            task_queue=original_queue,
            worker_environment=TemporalWorkerEnvironment.INTERNAL,
        )

        # Mock temporal_client() to return a fake client
        mocker.patch.object(executor, "temporal_client", new_callable=AsyncMock)

        # Mock get_task_manager().make_worker() to return an async context manager
        mock_task_manager = mocker.MagicMock()
        mock_worker_ctx = AsyncMock()
        mock_worker_ctx.__aenter__ = AsyncMock(return_value=None)
        mock_worker_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_task_manager.make_worker.return_value = mock_worker_ctx
        mocker.patch(
            "pipelex.deep_flow.tprl.conditional_worker.get_task_manager",
            return_value=mock_task_manager,
        )

        # Define a decorated method
        @with_conditional_worker
        async def fake_execute_workflow(_self_arg: WorkflowExecutor[Any, Any]) -> str:  # noqa: RUF029
            return "done"

        # Call multiple times on the same instance
        for _index in range(5):
            result = await fake_execute_workflow(executor)
            assert result == "done"
            assert executor.task_queue == original_queue, f"task_queue mutated after call: expected {original_queue!r}, got {executor.task_queue!r}"

    async def test_task_queue_restored_after_exception(self, mocker: MockerFixture) -> None:
        """task_queue must be restored even when the wrapped function raises."""
        original_queue = "error-queue"

        executor: WorkflowExecutor[Any, Any] = WorkflowExecutor(
            task_queue=original_queue,
            worker_environment=TemporalWorkerEnvironment.INTERNAL,
        )

        mocker.patch.object(executor, "temporal_client", new_callable=AsyncMock)

        mock_task_manager = mocker.MagicMock()
        mock_worker_ctx = AsyncMock()
        mock_worker_ctx.__aenter__ = AsyncMock(return_value=None)
        mock_worker_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_task_manager.make_worker.return_value = mock_worker_ctx
        mocker.patch(
            "pipelex.deep_flow.tprl.conditional_worker.get_task_manager",
            return_value=mock_task_manager,
        )

        @with_conditional_worker
        async def failing_execute_workflow(_self_arg: WorkflowExecutor[Any, Any]) -> str:  # noqa: RUF029
            msg = "workflow failed"
            raise RuntimeError(msg)

        with pytest.raises(RuntimeError, match="workflow failed"):
            await failing_execute_workflow(executor)

        assert executor.task_queue == original_queue, (
            f"task_queue not restored after exception: expected {original_queue!r}, got {executor.task_queue!r}"
        )
