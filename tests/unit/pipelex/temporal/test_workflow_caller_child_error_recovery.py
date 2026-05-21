"""Unit tests for the child-workflow boundary of ``WorkflowExecutor``.

When a child workflow fails, ``ChildWorkflowError`` exposes the deserialized
failure via ``.cause``. ``execute_child_workflow`` / ``start_child_workflow``
recover the structured ``ErrorReport`` packed by the activity bridge and carry
it on the ``WorkflowExecutionError`` — mirroring the ``execute_workflow`` path —
so the classification survives the child-workflow hop. A cause carrying no
report payload, malformed details, or a non-``ApplicationError`` cause all fall
back to a generic error.
"""

from typing import Any

import pytest
from pytest_mock import MockerFixture
from temporalio import workflow
from temporalio.exceptions import ApplicationError, ChildWorkflowError
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


def _child_workflow_error(cause: BaseException) -> ChildWorkflowError:
    """Build a ``ChildWorkflowError`` whose ``.cause`` is the deserialized failure."""
    error = ChildWorkflowError(
        "child workflow execution error",
        namespace="default",
        workflow_id="ut-child",
        run_id="ut-run",
        workflow_type="WfPipeRun",
        initiated_event_id=1,
        started_event_id=2,
        retry_state=None,
    )
    error.__cause__ = cause
    return error


@pytest.mark.asyncio(loop_scope="class")
class TestWorkflowCallerChildErrorRecovery:
    @pytest.mark.parametrize(
        "method_name",
        [
            pytest.param("execute_child_workflow", id="execute"),
            pytest.param("start_child_workflow", id="start"),
        ],
    )
    async def test_child_application_error_with_report_recovers_classification(self, mocker: MockerFixture, method_name: str) -> None:
        """A categorized child-workflow failure surfaces as a fully classified ``WorkflowExecutionError``."""
        app_error = ApplicationError("rate limited on the worker", _FULL_REPORT.to_dict(), type="CogtError")
        mocker.patch.object(workflow, method_name, new=mocker.AsyncMock(side_effect=_child_workflow_error(app_error)))
        executor = WorkflowExecutor[Any, Any](task_queue="test-queue")

        with pytest.raises(WorkflowExecutionError) as exc_info:
            await getattr(executor, method_name)(workflow_class=_StubWorkflow, workflow_arg={}, workflow_id="ut-run")

        error = exc_info.value
        # The real failure message replaces the generic "Failed to ... child workflow ...".
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

    @pytest.mark.parametrize(
        "method_name",
        [
            pytest.param("execute_child_workflow", id="execute"),
            pytest.param("start_child_workflow", id="start"),
        ],
    )
    async def test_g3_malformed_report_details_synthesizes_unrecoverable(self, mocker: MockerFixture, method_name: str) -> None:
        """G3 — a child ``ApplicationError`` whose details fail validation synthesizes the unrecoverable report.

        After Item D-1, ``recover_error_report`` is total — there is no longer a
        Pipelex-framed ``"Application error in child workflow X"`` fallback when
        details validation fails. The ``WorkflowExecutionError`` carries an
        ``UnrecoverableWorkflowFailureError`` report.
        """
        malformed = {"error_type": "X", "message": "m", "retryable": ["not", "a", "bool"]}
        app_error = ApplicationError("worker failure", malformed, type="CogtError")
        mocker.patch.object(workflow, method_name, new=mocker.AsyncMock(side_effect=_child_workflow_error(app_error)))
        executor = WorkflowExecutor[Any, Any](task_queue="test-queue")

        with pytest.raises(WorkflowExecutionError) as exc_info:
            await getattr(executor, method_name)(workflow_class=_StubWorkflow, workflow_arg={}, workflow_id="ut-run")

        error = exc_info.value
        assert error.error_report is not None
        assert error.error_report.error_type == "UnrecoverableWorkflowFailureError"
        assert "worker failure" in error.message

    @pytest.mark.parametrize(
        "method_name",
        [
            pytest.param("execute_child_workflow", id="execute"),
            pytest.param("start_child_workflow", id="start"),
        ],
    )
    async def test_g4_application_error_without_report_details_synthesizes_unrecoverable(self, mocker: MockerFixture, method_name: str) -> None:
        """G4 — a child ``ApplicationError`` carrying no report payload synthesizes the unrecoverable report."""
        app_error = ApplicationError("worker failure", type="RuntimeError")
        mocker.patch.object(workflow, method_name, new=mocker.AsyncMock(side_effect=_child_workflow_error(app_error)))
        executor = WorkflowExecutor[Any, Any](task_queue="test-queue")

        with pytest.raises(WorkflowExecutionError) as exc_info:
            await getattr(executor, method_name)(workflow_class=_StubWorkflow, workflow_arg={}, workflow_id="ut-run")

        error = exc_info.value
        assert error.error_report is not None
        assert error.error_report.error_type == "UnrecoverableWorkflowFailureError"
        assert "worker failure" in error.message

    @pytest.mark.parametrize(
        ("method_name", "generic_message"),
        [
            pytest.param("execute_child_workflow", "Failed to execute child workflow _StubWorkflow", id="execute"),
            pytest.param("start_child_workflow", "Failed to start child workflow _StubWorkflow", id="start"),
        ],
    )
    async def test_non_application_error_cause_stays_generic(self, mocker: MockerFixture, method_name: str, generic_message: str) -> None:
        """A child failure whose ``.cause`` is not an ``ApplicationError`` falls back to a generic error."""
        cause = RuntimeError("worker crashed hard")
        mocker.patch.object(workflow, method_name, new=mocker.AsyncMock(side_effect=_child_workflow_error(cause)))
        executor = WorkflowExecutor[Any, Any](task_queue="test-queue")

        with pytest.raises(WorkflowExecutionError) as exc_info:
            await getattr(executor, method_name)(workflow_class=_StubWorkflow, workflow_arg={}, workflow_id="ut-run")

        error = exc_info.value
        assert error.error_report is None
        assert error.message == generic_message
