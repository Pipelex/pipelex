"""Unit tests for the backend-neutral ``AsyncExecutionNotEnabledError`` guard.

Two boundaries must fail fast with a classifiable ``PipelexError`` when no
async execution backend is enabled on the deployment:

1. ``with_conditional_worker`` — the dispatch decorator on every
   ``WorkflowExecutor`` entry point (``TemporalPipeRun.run`` /
   ``TemporalPipeRun.start`` / ``TemporalPipeRouter._run_pipe_job``). The
   guard fires inside the wrapper *before* the per-environment ``match``
   block, so on the ``INTERNAL`` path it also precedes the worker bootstrap
   (``self.temporal_client()`` + ``make_worker(...)``) and on the
   ``EXTERNAL`` path it precedes the wrapped body. Without the guard the
   disabled path either leaks an opaque ``RuntimeError`` from the
   ``TemporalManager`` singleton accessor (``stamp_submitter_session_id``
   reads ``get_temporal_manager().session_id`` on its first line) or — on
   ``INTERNAL`` — falls through to ``temporal_client()``'s lower-level check,
   silently inverting the facade docstring contract.
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

    async def test_temporal_pipe_run_start_external_raises_before_touching_manager(self, mocker: MockerFixture) -> None:
        """``TemporalPipeRun.start()`` on the ``EXTERNAL`` path must raise the
        error before reaching ``stamp_submitter_session_id`` — which reads the
        ``TemporalManager`` singleton, only initialized when the async backend
        is enabled. The patched stamper records calls; if the guard ever
        regresses, the stamper will be called and this test will fail.
        """
        mocker.patch("pipelex.temporal.tprl.conditional_worker.get_config", return_value=_disabled_config_root(mocker))
        stamper = mocker.patch("pipelex.temporal.tprl_pipe.temporal_pipe_run.stamp_submitter_session_id")
        pipe_run = TemporalPipeRun(task_queue="ut-queue", worker_environment=TemporalWorkerEnvironment.EXTERNAL)

        with pytest.raises(AsyncExecutionNotEnabledError):
            await pipe_run.start(pipe_job=mocker.MagicMock())

        stamper.assert_not_called()

    async def test_temporal_pipe_run_run_external_raises_before_touching_manager(self, mocker: MockerFixture) -> None:
        """Same guarantee as ``start()`` for the blocking ``run()`` entry point on ``EXTERNAL``."""
        mocker.patch("pipelex.temporal.tprl.conditional_worker.get_config", return_value=_disabled_config_root(mocker))
        stamper = mocker.patch("pipelex.temporal.tprl_pipe.temporal_pipe_run.stamp_submitter_session_id")
        pipe_run = TemporalPipeRun(task_queue="ut-queue", worker_environment=TemporalWorkerEnvironment.EXTERNAL)

        with pytest.raises(AsyncExecutionNotEnabledError):
            await pipe_run.run(pipe_job=mocker.MagicMock())

        stamper.assert_not_called()

    async def test_temporal_pipe_run_start_internal_raises_before_worker_bootstrap(self, mocker: MockerFixture) -> None:
        """On the ``INTERNAL`` path the decorator does ``await self.temporal_client()``
        + ``make_worker(...)`` before calling the wrapped body. The guard must
        fire ahead of that bootstrap so a disabled deployment never reaches
        either — otherwise the facade-level guarantee degrades to
        ``temporal_client()``'s lower-level check, silently inverting the
        docstring contract. The ``temporal_client`` and ``make_worker`` patches
        are tripwires: a call on the disabled path is the regression.
        """
        mocker.patch("pipelex.temporal.tprl.conditional_worker.get_config", return_value=_disabled_config_root(mocker))
        temporal_client = mocker.patch.object(TemporalPipeRun, "temporal_client")
        make_worker = mocker.patch("pipelex.temporal.tprl.conditional_worker.get_task_manager")
        stamper = mocker.patch("pipelex.temporal.tprl_pipe.temporal_pipe_run.stamp_submitter_session_id")
        pipe_run = TemporalPipeRun(task_queue="ut-queue", worker_environment=TemporalWorkerEnvironment.INTERNAL)

        with pytest.raises(AsyncExecutionNotEnabledError):
            await pipe_run.start(pipe_job=mocker.MagicMock())

        temporal_client.assert_not_called()
        make_worker.assert_not_called()
        stamper.assert_not_called()

    async def test_temporal_pipe_run_run_internal_raises_before_worker_bootstrap(self, mocker: MockerFixture) -> None:
        """Same INTERNAL-path guarantee as ``start()`` for the blocking ``run()`` entry point."""
        mocker.patch("pipelex.temporal.tprl.conditional_worker.get_config", return_value=_disabled_config_root(mocker))
        temporal_client = mocker.patch.object(TemporalPipeRun, "temporal_client")
        make_worker = mocker.patch("pipelex.temporal.tprl.conditional_worker.get_task_manager")
        stamper = mocker.patch("pipelex.temporal.tprl_pipe.temporal_pipe_run.stamp_submitter_session_id")
        pipe_run = TemporalPipeRun(task_queue="ut-queue", worker_environment=TemporalWorkerEnvironment.INTERNAL)

        with pytest.raises(AsyncExecutionNotEnabledError):
            await pipe_run.run(pipe_job=mocker.MagicMock())

        temporal_client.assert_not_called()
        make_worker.assert_not_called()
        stamper.assert_not_called()

    async def test_decorator_skips_guard_when_inside_temporal_workflow(self, mocker: MockerFixture) -> None:
        """When ``with_conditional_worker`` is invoked from inside a Temporal
        workflow context (the child-dispatch path through
        ``TemporalPipeRouter._run_pipe_job``), the deployment-level guard must
        be skipped: being inside a workflow proves the backend is already
        running, and ``get_config()`` is unsafe to read from the workflow
        sandbox (it returns a separate, unconfigured copy on which
        ``temporal.is_enabled`` reads False — which would otherwise fail the
        child dispatch with ``AsyncExecutionNotEnabledError``).

        Reproduces the integration-temporal regression that surfaced in
        ``library_crate`` / ``tracing`` after the guard was first moved into
        the decorator without the workflow-context bypass.
        """
        from pipelex.temporal.tprl.conditional_worker import with_conditional_worker  # noqa: PLC0415

        mocker.patch("pipelex.temporal.tprl.conditional_worker.get_config", return_value=_disabled_config_root(mocker))
        mocker.patch("pipelex.temporal.tprl.conditional_worker.is_in_temporal_workflow", return_value=True)
        body_calls: list[WorkflowExecutor[Any, Any]] = []

        @with_conditional_worker
        async def fake_execute_workflow(self_arg: WorkflowExecutor[Any, Any]) -> str:  # noqa: RUF029
            body_calls.append(self_arg)
            return "ok"

        executor: WorkflowExecutor[Any, Any] = WorkflowExecutor(
            task_queue="ut-queue",
            worker_environment=TemporalWorkerEnvironment.EXTERNAL,
        )
        result = await fake_execute_workflow(executor)

        assert result == "ok"
        assert body_calls == [executor]

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
