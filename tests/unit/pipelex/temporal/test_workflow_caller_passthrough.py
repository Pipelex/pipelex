"""Unit tests for the additive ``search_attributes`` / ``static_summary`` /
``static_details`` / ``memo`` pass-through on every ``WorkflowExecutor`` entry
point.

Phase 1 of the Temporal IDs and Naming redesign extends the executor's surface
so the workflow-layer (Phase 3) can set the observability attributes on every
workflow start, both top-level and child. These tests pin the wiring: the four
kwargs given to the executor reach the underlying SDK call unchanged.
"""

from typing import Any

import pytest
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex.temporal.tprl.workflow_caller import WorkflowClass, WorkflowExecutor


class _StubWorkflow(WorkflowClass[Any, Any]):
    @override
    async def run(self, workflow_arg: Any) -> Any:  # pragma: no cover - never actually invoked
        return workflow_arg


_SEARCH_ATTRS = {"PipeCode": ["translate_doc"], "DomainCode": ["documents"]}
_SUMMARY = "translate_doc — Translate EN→FR"
_DETAILS = "| Field | Value |\n|---|---|\n| Pipe | `translate_doc` |"
_MEMO = {"pipelex": {"library_crate": "documents@2.1.4"}}


def _make_executor_with_stub_client(mocker: MockerFixture) -> tuple[WorkflowExecutor[Any, Any], Any]:
    """Build a ``WorkflowExecutor`` whose ``temporal_client()`` returns a stub client.

    Returns the executor and the stub client so tests can read ``call_args`` from
    the methods the executor invokes on the client.
    """
    stub_client = mocker.MagicMock()
    mocker.patch.object(WorkflowExecutor, "temporal_client", new=mocker.AsyncMock(return_value=stub_client))
    return WorkflowExecutor[Any, Any](task_queue="test-queue"), stub_client


@pytest.mark.asyncio(loop_scope="class")
class TestWorkflowCallerPassthrough:
    async def test_execute_workflow_passes_through_observability_kwargs(self, mocker: MockerFixture) -> None:
        executor, client = _make_executor_with_stub_client(mocker)
        client.execute_workflow = mocker.AsyncMock(return_value="result")

        await executor.execute_workflow(
            workflow_class=_StubWorkflow,
            workflow_arg={"foo": "bar"},
            workflow_id="ut-test-run",
            search_attributes=_SEARCH_ATTRS,
            static_summary=_SUMMARY,
            static_details=_DETAILS,
            memo=_MEMO,
        )

        kwargs = client.execute_workflow.call_args.kwargs
        assert kwargs.get("search_attributes") == _SEARCH_ATTRS
        assert kwargs.get("static_summary") == _SUMMARY
        assert kwargs.get("static_details") == _DETAILS
        assert kwargs.get("memo") == _MEMO

    async def test_start_workflow_passes_through_observability_kwargs(self, mocker: MockerFixture) -> None:
        executor, client = _make_executor_with_stub_client(mocker)
        client.start_workflow = mocker.AsyncMock(return_value=mocker.MagicMock())

        await executor.start_workflow(
            workflow_class=_StubWorkflow,
            workflow_arg={"foo": "bar"},
            workflow_id="ut-test-run",
            search_attributes=_SEARCH_ATTRS,
            static_summary=_SUMMARY,
            static_details=_DETAILS,
            memo=_MEMO,
        )

        kwargs = client.start_workflow.call_args.kwargs
        assert kwargs.get("search_attributes") == _SEARCH_ATTRS
        assert kwargs.get("static_summary") == _SUMMARY
        assert kwargs.get("static_details") == _DETAILS
        assert kwargs.get("memo") == _MEMO

    async def test_execute_child_workflow_passes_through_observability_kwargs(self, mocker: MockerFixture) -> None:
        executor, _ = _make_executor_with_stub_client(mocker)
        mock_execute_child = mocker.patch("temporalio.workflow.execute_child_workflow", new_callable=mocker.AsyncMock)
        mock_execute_child.return_value = "child-result"

        await executor.execute_child_workflow(
            workflow_class=_StubWorkflow,
            workflow_arg={"foo": "bar"},
            workflow_id="ut-test-run/pipe-router",
            search_attributes=_SEARCH_ATTRS,
            static_summary=_SUMMARY,
            static_details=_DETAILS,
            memo=_MEMO,
        )

        kwargs = mock_execute_child.call_args.kwargs
        assert kwargs.get("search_attributes") == _SEARCH_ATTRS
        assert kwargs.get("static_summary") == _SUMMARY
        assert kwargs.get("static_details") == _DETAILS
        assert kwargs.get("memo") == _MEMO

    async def test_start_child_workflow_passes_through_observability_kwargs(self, mocker: MockerFixture) -> None:
        executor, _ = _make_executor_with_stub_client(mocker)
        mock_start_child = mocker.patch("temporalio.workflow.start_child_workflow", new_callable=mocker.AsyncMock)
        mock_start_child.return_value = mocker.MagicMock()

        await executor.start_child_workflow(
            workflow_class=_StubWorkflow,
            workflow_arg={"foo": "bar"},
            workflow_id="ut-test-run/pipe-router",
            search_attributes=_SEARCH_ATTRS,
            static_summary=_SUMMARY,
            static_details=_DETAILS,
            memo=_MEMO,
        )

        kwargs = mock_start_child.call_args.kwargs
        assert kwargs.get("search_attributes") == _SEARCH_ATTRS
        assert kwargs.get("static_summary") == _SUMMARY
        assert kwargs.get("static_details") == _DETAILS
        assert kwargs.get("memo") == _MEMO
