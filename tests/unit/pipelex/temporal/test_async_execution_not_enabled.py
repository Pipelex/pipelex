"""Unit tests for the backend-neutral ``AsyncExecutionNotEnabledError`` guard.

Two dispatch entry points must fail fast with a classifiable
``PipelexError`` when no async execution backend is enabled on the deployment:

1. ``TemporalPipeRun.run()`` / ``TemporalPipeRun.start()`` — these read the
   ``TemporalManager`` singleton on their first line (via
   ``stamp_submitter_session_id``). Without the guard the disabled path leaks
   an opaque ``RuntimeError`` from the singleton accessor instead of a
   classified ``PipelexError`` — downstream HTTP / CLI layers then degrade it
   to a generic 500.
2. ``WorkflowExecutor.temporal_client()`` — kept on the path for callers that
   reach the executor directly rather than through the pipe-run facade.

The error class is backend-neutral on purpose (it is shared with future async
backends like Mistral Workflows), so the assertions pin classification, not
backend-specific copy.
"""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.base_exceptions import ErrorDomain
from pipelex.pipe_run.exceptions import AsyncExecutionNotEnabledError
from pipelex.temporal.temporal_manager import TemporalWorkerEnvironment
from pipelex.temporal.tprl.workflow_caller import WorkflowExecutor
from pipelex.temporal.tprl_pipe.temporal_pipe_run import TemporalPipeRun


def _disabled_config_root(mocker: MockerFixture) -> Any:
    """A minimal ``get_config()`` stub whose ``temporal.is_enabled`` reads False."""
    config_root = mocker.MagicMock()
    config_root.temporal.is_enabled = False
    return config_root


@pytest.mark.asyncio(loop_scope="class")
class TestAsyncExecutionNotEnabled:
    async def test_error_classification(self) -> None:
        """The error reports as ``CONFIG``-domain with a stable error_type and
        a curated title — these three fields are the API and CLI contract.

        Declared ``async`` only to share the class-level
        ``@pytest.mark.asyncio(loop_scope="class")`` mark with the dispatch
        tests below (the project rule is one ``TestClass`` per module).
        """
        exc = AsyncExecutionNotEnabledError("anything")
        report = exc.to_error_report()

        assert report.error_type == "AsyncExecutionNotEnabledError"
        assert report.title == "Async execution not enabled"
        assert report.error_domain == ErrorDomain.CONFIG

    async def test_temporal_pipe_run_start_raises_before_touching_manager(self, mocker: MockerFixture) -> None:
        """``TemporalPipeRun.start()`` must raise the new error before the first
        ``stamp_submitter_session_id`` line — that line reads the
        ``TemporalManager`` singleton, which is only initialized when the async
        backend is enabled. If the guard ever regresses, the patched stamper
        below will record a call and this test will fail.
        """
        mocker.patch("pipelex.temporal.tprl_pipe.temporal_pipe_run.get_config", return_value=_disabled_config_root(mocker))
        stamper = mocker.patch("pipelex.temporal.tprl_pipe.temporal_pipe_run.stamp_submitter_session_id")
        pipe_run = TemporalPipeRun(task_queue="ut-queue", worker_environment=TemporalWorkerEnvironment.EXTERNAL)

        with pytest.raises(AsyncExecutionNotEnabledError):
            await pipe_run.start(pipe_job=mocker.MagicMock())

        stamper.assert_not_called()

    async def test_temporal_pipe_run_run_raises_before_touching_manager(self, mocker: MockerFixture) -> None:
        """Same guarantee as ``start()`` for the blocking ``run()`` entry point."""
        mocker.patch("pipelex.temporal.tprl_pipe.temporal_pipe_run.get_config", return_value=_disabled_config_root(mocker))
        stamper = mocker.patch("pipelex.temporal.tprl_pipe.temporal_pipe_run.stamp_submitter_session_id")
        pipe_run = TemporalPipeRun(task_queue="ut-queue", worker_environment=TemporalWorkerEnvironment.EXTERNAL)

        with pytest.raises(AsyncExecutionNotEnabledError):
            await pipe_run.run(pipe_job=mocker.MagicMock())

        stamper.assert_not_called()

    async def test_workflow_caller_temporal_client_raises_when_disabled(self, mocker: MockerFixture) -> None:
        """``WorkflowExecutor.temporal_client()`` is the lower-level entry point
        callers reach when they wire the executor directly. The same guard
        applies there so a disabled-backend deployment never reaches the
        ``temporalio`` client construction code.
        """
        mocker.patch("pipelex.temporal.tprl.workflow_caller.get_config", return_value=_disabled_config_root(mocker))
        executor: WorkflowExecutor[Any, Any] = WorkflowExecutor(task_queue="ut-queue")

        with pytest.raises(AsyncExecutionNotEnabledError):
            await executor.temporal_client()
