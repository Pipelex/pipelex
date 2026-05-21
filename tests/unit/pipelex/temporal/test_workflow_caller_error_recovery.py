"""Unit tests for ``WorkflowExecutor.execute_workflow``'s error path.

When ``client.execute_workflow`` raises a ``WorkflowFailureError``, the executor
recovers the structured ``ErrorReport`` packed by the activity bridge and
carries it on the ``WorkflowExecutionError`` — so the classification survives
the workflow → submitter hop instead of flooring to a generic ``RUNTIME`` error.
``WorkflowAlreadyStartedError`` / ``RPCError`` go through the sibling clause and
stay generic.
"""

from typing import Any

import pytest
from pytest_mock import MockerFixture
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ApplicationError, WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode
from typing_extensions import override

from pipelex.base_exceptions import ErrorDomain, ErrorReport
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.temporal.exceptions import WorkflowExecutionError
from pipelex.temporal.tprl.workflow_caller import WorkflowClass, WorkflowExecutor

_FULL_REPORT = ErrorReport(
    error_type="CogtError",
    message="rate limited on the worker",
    title="AI inference failed",
    type_uri="https://docs.pipelex.com/latest/errors/cogt-error/",
    error_category="capacity",
    error_domain=ErrorDomain.RUNTIME,
    retryable=False,
    user_action=UserAction(kind=UserActionKind.CHECK_BILLING, detail="check your billing page"),
    model="gpt-5",
    provider="openai",
)


class _StubWorkflow(WorkflowClass[Any, Any]):
    @override
    async def run(self, workflow_arg: Any) -> Any:  # pragma: no cover - never actually invoked
        return workflow_arg


def _make_executor_with_stub_client(mocker: MockerFixture) -> tuple[WorkflowExecutor[Any, Any], Any]:
    """Build a ``WorkflowExecutor`` whose ``temporal_client()`` returns a stub client."""
    stub_client = mocker.MagicMock()
    mocker.patch.object(WorkflowExecutor, "temporal_client", new=mocker.AsyncMock(return_value=stub_client))
    return WorkflowExecutor[Any, Any](task_queue="test-queue"), stub_client


def _workflow_failure_with_report() -> WorkflowFailureError:
    """A ``WorkflowFailureError`` carrying the activity-bridge report payload."""
    app_error = ApplicationError("rate limited on the worker", _FULL_REPORT.to_dict(), type="CogtError")
    return WorkflowFailureError(cause=app_error)


@pytest.mark.asyncio(loop_scope="class")
class TestWorkflowCallerErrorRecovery:
    async def test_workflow_failure_with_report_recovers_classification_and_real_message(self, mocker: MockerFixture) -> None:
        """A categorized worker failure surfaces as a fully classified ``WorkflowExecutionError``."""
        executor, client = _make_executor_with_stub_client(mocker)
        client.execute_workflow = mocker.AsyncMock(side_effect=_workflow_failure_with_report())

        with pytest.raises(WorkflowExecutionError) as exc_info:
            await executor.execute_workflow(workflow_class=_StubWorkflow, workflow_arg={}, workflow_id="ut-run")

        error = exc_info.value
        # The real failure message replaces the generic "Failed to execute workflow ...".
        assert error.message == "rate limited on the worker"
        assert error.error_report is not None
        report = error.to_error_report()
        assert report.message == "rate limited on the worker"
        assert report.error_category == "capacity"
        assert report.retryable is False
        assert report.model == "gpt-5"
        assert report.provider == "openai"
        assert report.user_action is not None
        assert report.user_action.kind == UserActionKind.CHECK_BILLING

    async def test_workflow_failure_without_report_synthesizes_unrecoverable(self, mocker: MockerFixture) -> None:
        """A non-Pipelex workflow failure (no packed report) surfaces as a synthesized unrecoverable report.

        After Item D-1, ``recover_error_report`` is total — there is no longer a
        Pipelex-framed ``"Failed to execute workflow X"`` fallback. The
        ``WorkflowExecutionError`` carries a stable-identity
        ``UnrecoverableWorkflowFailureError`` report whose message preserves the
        underlying exception text. The legacy framing is gone on purpose: the
        new message is strictly more diagnostic.
        """
        executor, client = _make_executor_with_stub_client(mocker)
        failure = WorkflowFailureError(cause=RuntimeError("worker crashed hard"))
        client.execute_workflow = mocker.AsyncMock(side_effect=failure)

        with pytest.raises(WorkflowExecutionError) as exc_info:
            await executor.execute_workflow(workflow_class=_StubWorkflow, workflow_arg={}, workflow_id="ut-run")

        error = exc_info.value
        assert error.error_report is not None
        assert error.error_report.error_type == "UnrecoverableWorkflowFailureError"
        assert error.error_report.error_domain == ErrorDomain.RUNTIME
        # Synthesized message preserves the underlying exception text, NOT the
        # legacy "Failed to execute workflow _StubWorkflow" framing.
        assert "worker crashed hard" in error.message
        assert error.message != "Failed to execute workflow _StubWorkflow"

    @pytest.mark.parametrize(
        "side_effect",
        [
            pytest.param(WorkflowAlreadyStartedError(workflow_id="ut-run", workflow_type="WfPipeRun"), id="already-started"),
            pytest.param(RPCError("temporal server unavailable", RPCStatusCode.UNAVAILABLE, b""), id="rpc-error"),
        ],
    )
    async def test_g6_already_started_and_rpc_error_stay_generic(self, mocker: MockerFixture, side_effect: BaseException) -> None:
        """G6 — the ``WorkflowAlreadyStartedError`` / ``RPCError`` clause stays generic, ``error_report=None``."""
        executor, client = _make_executor_with_stub_client(mocker)
        client.execute_workflow = mocker.AsyncMock(side_effect=side_effect)

        with pytest.raises(WorkflowExecutionError) as exc_info:
            await executor.execute_workflow(workflow_class=_StubWorkflow, workflow_arg={}, workflow_id="ut-run")

        error = exc_info.value
        assert error.error_report is None
        assert error.message == "Failed to execute workflow _StubWorkflow"
