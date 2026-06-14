"""Regression tests for the Temporal workflow-level fail-safe floor.

The error-handling bridge converts every error that crosses an *activity*
boundary into a terminal, classified Temporal failure. But a pipelex domain
error raised **inline in workflow code** — never dispatched through an activity —
is neither an ``ActivityError`` nor an ``ApplicationError``. Without a backstop
Temporal treats it as a *workflow-task* failure and retries the task
indefinitely: a silent, resource-burning hang that only surfaces (as the wrong,
generic timeout error) after the workflow execution timeout.

These tests pin the floor that closes that hole:

- ``WfPipeRouter`` converts an escaping ``PipelexError`` to a terminal
  ``TemporalError`` carrying the structured ``ErrorReport`` (rich path).
- ``WfPipeRun`` routes an inline ``PipelexError`` through its deferred-delivery
  path so the FAILED webhook still fires, then re-raises terminally.
- The worker's ``workflow_failure_exception_types`` includes ``PipelexError`` so
  even an *uncaught* domain error fails the workflow terminally (the floor) with
  a synthesized report, rather than hanging.

Every case sets a short ``workflow_execution_timeout`` so a regression that
reopens the hole fails fast (and on the wrong, timeout-shaped classification)
instead of hanging the suite for the full default budget.
"""

import uuid
from collections.abc import Generator
from datetime import timedelta
from typing import Any

import pytest
from pytest_mock import MockerFixture
from temporalio import workflow
from temporalio.client import Client as TemporalClient
from temporalio.common import RetryPolicy

from pipelex.config import get_config
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, DeliveryStatus, WebhookTarget
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.runtime_bridge.primitives.pipe_run_arg import PipeRunArg
from pipelex.temporal.exceptions import WorkflowExecutionError, WorkflowInputError
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl.temporal_error import TemporalError
from pipelex.temporal.tprl.workflow_caller import WorkflowExecutor
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from pipelex.temporal.tprl_pipe.wf_pipe_run import WfPipeRun
from tests.integration.pipelex.error_handling.test_data import ErrorReportParityTestData
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle

# Bounds the regression hang: with the fail-safe in place every case fails
# near-instantly; only a regression that reopens the workflow-task-retry hole
# would consume this budget before surfacing a (wrong, timeout-shaped) error.
_FAILSAFE_EXECUTION_TIMEOUT = timedelta(seconds=30)

_RAW_INLINE_MESSAGE = "raw inline pipelex error, never caught"


@workflow.defn(name="wf_raw_pipelex_error_stub")
class WfRawPipelexErrorStub:
    """Workflow that raises a raw, uncaught ``PipelexError`` inline.

    Exercises the worker-level floor (``workflow_failure_exception_types``
    contains ``PipelexError``) — no workflow-level catch-all is involved, so the
    only thing that can make this terminal instead of a retrying task failure is
    the registration on the production ``make_worker``.
    """

    @workflow.run
    async def run(self, workflow_arg: PipeJob) -> PipeOutput:  # noqa: ARG002 - signature pinned by the WorkflowClass protocol; raises immediately
        raise WorkflowInputError(_RAW_INLINE_MESSAGE)


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWorkflowInlineErrorFailsafe:
    """A pipelex error escaping workflow code fails loud and classified, never hangs."""

    @pytest.fixture
    def temporal_enabled(self) -> Generator[None, None, None]:
        """Enable ``temporal.is_enabled`` so ``WorkflowExecutor.temporal_client()`` connects."""
        config = get_config()
        previous = config.temporal.is_enabled
        config.temporal = config.temporal.model_copy(update={"is_enabled": True})
        yield
        config.temporal = config.temporal.model_copy(update={"is_enabled": previous})

    @pytest.fixture
    def failing_pipe_job(self) -> Generator[PipeJob, None, None]:
        """A PipeJob in LIVE mode (the workflow runs the pipe instead of short-circuiting in dry mode)."""
        yield from pipe_job_from_bundle(
            bundle_file=ErrorReportParityTestData.BUNDLE_FILE,
            pipe_code=ErrorReportParityTestData.PIPE_CODE,
            pipe_run_mode=PipeRunMode.LIVE,
        )

    async def test_router_inline_pipelex_error_surfaces_classified_terminally(
        self,
        temporal_client: TemporalClient,
        mocker: MockerFixture,
        temporal_enabled: None,  # noqa: ARG002 - enables temporal.is_enabled for the duration
        failing_pipe_job: PipeJob,
    ) -> None:
        """A ``PipelexError`` raised inline by the pipe (no activity) surfaces fully classified, not as a hang."""
        # Make the pipe raise *inline* in the workflow event loop — the escape path the activity
        # bridge never sees. ``run_pipe`` is @final on PipeAbstract, so patching the base covers
        # whatever concrete pipe the bundle resolves to.
        mocker.patch.object(
            PipeAbstract,
            "run_pipe",
            new=mocker.AsyncMock(side_effect=ErrorReportParityTestData.make_failing_llm_error()),
        )

        task_queue = f"q_inline_router_{uuid.uuid4().hex[:8]}"
        workflow_id = f"wf_inline_router_{uuid.uuid4().hex[:8]}"
        executor: WorkflowExecutor[PipeJob, PipeOutput] = WorkflowExecutor(
            temporal_client=temporal_client,
            task_queue=task_queue,
            retry_policy=RetryPolicy(maximum_attempts=1),
            workflow_execution_timeout=_FAILSAFE_EXECUTION_TIMEOUT,
        )

        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            with pytest.raises(WorkflowExecutionError) as exc_info:
                await executor.execute_workflow(
                    workflow_class=WfPipeRouter,
                    workflow_arg=failing_pipe_job,
                    workflow_id=workflow_id,
                )

        error = exc_info.value
        assert error.error_report is not None
        report = error.to_error_report()
        # The rich classification of the *inline* error survived — proving it went through the
        # fail-safe conversion, not the regression timeout path (which would synthesize an
        # UnrecoverableWorkflowFailureError instead).
        assert report.error_type == "LLMCompletionError"
        assert ErrorReportParityTestData.FAILURE_MESSAGE in report.message
        assert report.error_category == ErrorReportParityTestData.FAILURE_CATEGORY
        assert report.retryable == ErrorReportParityTestData.EXPECTED_RETRYABLE
        assert report.model == ErrorReportParityTestData.FAILURE_MODEL
        assert report.provider == ErrorReportParityTestData.FAILURE_PROVIDER
        assert report.user_action is not None
        assert report.user_action.kind == ErrorReportParityTestData.EXPECTED_USER_ACTION_KIND

    async def test_router_already_terminal_error_propagates_untouched_preserving_leaf_classification(
        self,
        temporal_client: TemporalClient,
        mocker: MockerFixture,
        temporal_enabled: None,  # noqa: ARG002 - enables temporal.is_enabled for the duration
        failing_pipe_job: PipeJob,
    ) -> None:
        """An escaping error that ALREADY carries a Temporal failure propagates untouched.

        Pins the ``_carries_temporal_failure`` True branch — the reachable case where a controller
        pipe's sub-pipe fails as a child workflow and ``TemporalPipeRouter`` wraps the
        ``ChildWorkflowError`` as ``WorkflowExecutionError``, which then escapes the parent's
        ``pipe.run_pipe``. The rich leaf report rides an ``ApplicationError`` (a Temporal
        ``FailureError``) in the ``__cause__`` chain and is recoverable only by
        ``recover_error_report`` at the submitter. A regression that negated or deleted the guard
        would convert it via ``from_message_exception`` instead, flattening ``error_type`` to
        ``WorkflowExecutionError`` and dropping model / provider / category — so these assertions
        fail loudly on exactly that regression (the convert-branch sibling test above would still
        pass, which is why this branch needs its own coverage).
        """
        # The structured leaf report the nested failure carries, built like the activity bridge:
        # an LLMCompletionError -> ErrorReport -> dict, packed into ApplicationError.details.
        leaf_report_dict = ErrorReportParityTestData.make_failing_llm_error().to_error_report().to_dict()
        # The already-terminal carrier: a TemporalError IS an ApplicationError (a Temporal
        # FailureError) holding the leaf report in details — what sits in the chain after a child
        # WfPipeRouter fails. Wrapped via ``from`` as WorkflowExecutionError, mirroring
        # TemporalPipeRouter's ``raise WorkflowExecutionError(...) from ChildWorkflowError``.
        already_terminal = TemporalError(
            message=ErrorReportParityTestData.FAILURE_MESSAGE,
            error_type="LLMCompletionError",
            non_retryable=True,
            error_report=leaf_report_dict,
        )
        nested_failure = WorkflowExecutionError("nested sub-pipe failed")
        nested_failure.__cause__ = already_terminal
        mocker.patch.object(
            PipeAbstract,
            "run_pipe",
            new=mocker.AsyncMock(side_effect=nested_failure),
        )

        task_queue = f"q_inline_passthrough_{uuid.uuid4().hex[:8]}"
        workflow_id = f"wf_inline_passthrough_{uuid.uuid4().hex[:8]}"
        executor: WorkflowExecutor[PipeJob, PipeOutput] = WorkflowExecutor(
            temporal_client=temporal_client,
            task_queue=task_queue,
            retry_policy=RetryPolicy(maximum_attempts=1),
            workflow_execution_timeout=_FAILSAFE_EXECUTION_TIMEOUT,
        )

        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            with pytest.raises(WorkflowExecutionError) as exc_info:
                await executor.execute_workflow(
                    workflow_class=WfPipeRouter,
                    workflow_arg=failing_pipe_job,
                    workflow_id=workflow_id,
                )

        report = exc_info.value.to_error_report()
        # The LEAF classification survived end-to-end: error_type is the leaf's, NOT
        # "WorkflowExecutionError" — proof the guard propagated the error untouched and let the
        # submitter recover the original report, rather than re-wrapping it into a generic one.
        assert report.error_type == "LLMCompletionError"
        assert ErrorReportParityTestData.FAILURE_MESSAGE in report.message
        assert report.error_category == ErrorReportParityTestData.FAILURE_CATEGORY
        assert report.retryable == ErrorReportParityTestData.EXPECTED_RETRYABLE
        assert report.model == ErrorReportParityTestData.FAILURE_MODEL
        assert report.provider == ErrorReportParityTestData.FAILURE_PROVIDER

    async def test_wf_pipe_run_inline_error_fires_failed_webhook_and_surfaces_classification(
        self,
        temporal_client: TemporalClient,
        mocker: MockerFixture,
        temporal_enabled: None,  # noqa: ARG002 - enables temporal.is_enabled for the duration
        failing_pipe_job: PipeJob,
    ) -> None:
        """An inline ``PipelexError`` in the parent workflow still fires the FAILED webhook and surfaces terminally."""
        # Force an inline domain error inside WfPipeRun itself — build_search_attributes is
        # evaluated as an argument to execute_child_workflow, before any child/activity exists.
        inline_error = WorkflowInputError("simulated inline search-attribute failure")
        mocker.patch(
            "pipelex.temporal.tprl_pipe.wf_pipe_run.build_search_attributes",
            side_effect=inline_error,
        )

        captured_webhook_payloads: list[dict[str, Any]] = []
        mock_httpx_client = mocker.AsyncMock()
        mock_response = mocker.MagicMock()
        mock_response.raise_for_status = mocker.Mock()
        mock_httpx_client.__aenter__ = mocker.AsyncMock(return_value=mock_httpx_client)
        mock_httpx_client.__aexit__ = mocker.AsyncMock(return_value=False)

        def capture_post(url: str, **kwargs: Any) -> Any:  # noqa: ARG001 - url is positional, unused
            captured_webhook_payloads.append(kwargs["json"])
            return mock_response

        mock_httpx_client.post = mocker.AsyncMock(side_effect=capture_post)
        mocker.patch("pipelex.pipe_run.delivery_executor.httpx.AsyncClient", return_value=mock_httpx_client)

        delivery_assignment = DeliveryAssignment(webhooks=[WebhookTarget(url="https://test.example.com/hook")])
        pipe_run_arg = PipeRunArg(pipe_job=failing_pipe_job, delivery_assignment=delivery_assignment).prepare_for_temporal()

        task_queue = f"q_inline_run_{uuid.uuid4().hex[:8]}"
        workflow_id = f"wf_inline_run_{uuid.uuid4().hex[:8]}"
        executor: WorkflowExecutor[PipeRunArg, PipeOutput] = WorkflowExecutor(
            temporal_client=temporal_client,
            task_queue=task_queue,
            retry_policy=RetryPolicy(maximum_attempts=1),
            workflow_execution_timeout=_FAILSAFE_EXECUTION_TIMEOUT,
        )

        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            with pytest.raises(WorkflowExecutionError) as exc_info:
                await executor.execute_workflow(
                    workflow_class=WfPipeRun,
                    workflow_arg=pipe_run_arg,
                    workflow_id=workflow_id,
                )

        # The FAILED webhook fired even though the failure never reached pipe execution — a terminal
        # failure must always notify the receiver, including on an inline workflow-setup error.
        assert len(captured_webhook_payloads) == 1, f"expected exactly one FAILED webhook, got {len(captured_webhook_payloads)}"
        payload = captured_webhook_payloads[0]
        assert payload["status"] == DeliveryStatus.FAILED
        assert "error" in payload, "FAILED delivery webhook must include the structured error report"
        assert payload["error"]["error_type"] == "WorkflowInputError"
        assert "simulated inline search-attribute failure" in payload["error"]["message"]

        # The submitter sees the same inline error, classified — not a generic timeout.
        submitter_error = exc_info.value
        assert submitter_error.error_report is not None
        assert submitter_error.error_report.error_type == "WorkflowInputError"
        assert "simulated inline search-attribute failure" in submitter_error.message

    async def test_uncaught_pipelex_error_fails_terminally_on_production_worker(
        self,
        temporal_client: TemporalClient,
        temporal_enabled: None,  # noqa: ARG002 - enables temporal.is_enabled for the duration
        failing_pipe_job: PipeJob,
    ) -> None:
        """The worker-level floor: a raw, uncaught ``PipelexError`` fails terminally instead of retrying forever."""
        task_queue = f"q_floor_{uuid.uuid4().hex[:8]}"
        workflow_id = f"wf_floor_{uuid.uuid4().hex[:8]}"
        executor: WorkflowExecutor[PipeJob, PipeOutput] = WorkflowExecutor(
            temporal_client=temporal_client,
            task_queue=task_queue,
            retry_policy=RetryPolicy(maximum_attempts=1),
            workflow_execution_timeout=_FAILSAFE_EXECUTION_TIMEOUT,
        )

        # Use the production make_worker so the assertion is against the real
        # workflow_failure_exception_types config, with the stub registered alongside it.
        async with get_task_manager().make_worker(
            temporal_client,
            task_queue=task_queue,
            is_not_sandboxed=True,
            test_workflows=[WfRawPipelexErrorStub],
        ):
            with pytest.raises(WorkflowExecutionError) as exc_info:
                await executor.execute_workflow(
                    workflow_class=WfRawPipelexErrorStub,
                    workflow_arg=failing_pipe_job,
                    workflow_id=workflow_id,
                )

        error = exc_info.value
        assert error.error_report is not None
        # No catch-all converted it, so the floor degrades to a synthesized report — but it is
        # terminal and preserves the original message, proving the workflow failed loud rather
        # than hanging (a hang would have surfaced a timeout message instead).
        assert error.error_report.error_type == "UnrecoverableWorkflowFailureError"
        assert _RAW_INLINE_MESSAGE in error.message
