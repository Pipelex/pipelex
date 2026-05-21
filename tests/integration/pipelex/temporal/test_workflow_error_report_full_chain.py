"""Temporal arm of the local / Temporal ``ErrorReport`` parity pair.

Runs the ``native_text_sequence`` pipe through a real ``WfPipeRouter`` workflow
on the in-process Temporal server, submitted via ``WorkflowExecutor.execute_workflow``,
with the activity-side LLM call mocked to fail. This exercises the genuine
activity → workflow → submitter serialization round-trip — the unit tests
(``tests/unit/pipelex/temporal/test_workflow_caller_error_recovery.py``) only
fake the ``WorkflowFailureError`` with a synthetic ``ApplicationError``.

It asserts the recovered ``ErrorReport`` carries the full classification
(``error_category`` / ``retryable`` / ``model`` / ``provider`` / ``user_action``)
and the real failure message — not the generic ``"Failed to execute workflow ..."``.

The local baseline is the separate module
``tests/integration/pipelex/error_handling/test_error_report_local_full_chain.py``;
both arms assert the same ``ErrorReportParityTestData`` constants, so local /
Temporal parity holds by construction.
"""

import uuid
from collections.abc import Generator
from typing import TYPE_CHECKING, Any

import pytest
from pytest_mock import MockerFixture
from temporalio.client import Client as TemporalClient
from temporalio.common import RetryPolicy

from pipelex.config import get_config
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, DeliveryStatus, WebhookTarget
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.temporal.exceptions import WorkflowExecutionError
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl.workflow_caller import WorkflowExecutor
from pipelex.temporal.tprl_pipe.pipe_run_arg import PipeRunArg
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from pipelex.temporal.tprl_pipe.wf_pipe_run import WfPipeRun
from tests.integration.pipelex.error_handling.test_data import ErrorReportParityTestData
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_output import PipeOutput

ACT_LLM_GEN_TEXT_TARGET = "pipelex.temporal.tprl_content_generation.act_llm_generate.llm_gen_text"


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWorkflowErrorReportFullChain:
    """A failing pipe's structured ``ErrorReport`` survives the Temporal workflow → submitter boundary."""

    @pytest.fixture
    def temporal_enabled(self) -> Generator[None, None, None]:
        """Enable ``temporal.is_enabled`` for the test — ``WorkflowExecutor.temporal_client()``
        raises when it is off. Mirrors the pattern in
        ``tests/integration/pipelex/temporal/content_generation/conftest.py``.
        """
        config = get_config()
        previous = config.temporal.is_enabled
        config.temporal = config.temporal.model_copy(update={"is_enabled": True})
        yield
        config.temporal = config.temporal.model_copy(update={"is_enabled": previous})

    @pytest.fixture
    def failing_pipe_job(self) -> Generator[PipeJob, None, None]:
        """A PipeJob for the failing pipe, in LIVE mode so the workflow dispatches the LLM activity.

        DRY mode short-circuits the ``act_llm_gen_text`` dispatch (the dry content generator
        reports inline inside the workflow), so the activity — and the mock — never fire.
        """
        yield from pipe_job_from_bundle(
            bundle_file=ErrorReportParityTestData.BUNDLE_FILE,
            pipe_code=ErrorReportParityTestData.PIPE_CODE,
            pipe_run_mode=PipeRunMode.LIVE,
        )

    async def test_error_report_survives_temporal_boundary(
        self,
        temporal_client: TemporalClient,
        mocker: MockerFixture,
        temporal_enabled: None,  # noqa: ARG002 - enables temporal.is_enabled for the duration
        failing_pipe_job: PipeJob,
    ) -> None:
        """A failing pipe run through Temporal surfaces a fully classified ``WorkflowExecutionError``."""
        # Mock the LLM call inside the real activity (in-process unsandboxed worker, same
        # process). @convert_pipelex_errors packs the ErrorReport into ApplicationError.details.
        mocker.patch(
            ACT_LLM_GEN_TEXT_TARGET,
            new=mocker.AsyncMock(side_effect=ErrorReportParityTestData.make_failing_llm_error()),
        )

        task_queue = f"q_err_fullchain_{uuid.uuid4().hex[:8]}"
        workflow_id = f"wf_err_fullchain_{uuid.uuid4().hex[:8]}"
        executor: WorkflowExecutor[PipeJob, PipeOutput] = WorkflowExecutor(
            temporal_client=temporal_client,
            task_queue=task_queue,
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            with pytest.raises(WorkflowExecutionError) as exc_info:
                await executor.execute_workflow(
                    workflow_class=WfPipeRouter,
                    workflow_arg=failing_pipe_job,
                    workflow_id=workflow_id,
                )

        error = exc_info.value
        # The structured report was recovered across the workflow → submitter boundary.
        assert error.error_report is not None
        report = error.to_error_report()

        # The real failure message survived — not the generic "Failed to execute workflow ...".
        assert ErrorReportParityTestData.FAILURE_MESSAGE in report.message
        assert "Failed to execute workflow" not in report.message

        # The full classification survived the Temporal serialization round-trip.
        assert report.error_category == ErrorReportParityTestData.FAILURE_CATEGORY
        assert report.retryable == ErrorReportParityTestData.EXPECTED_RETRYABLE
        assert report.model == ErrorReportParityTestData.FAILURE_MODEL
        assert report.provider == ErrorReportParityTestData.FAILURE_PROVIDER
        assert report.user_action is not None
        assert report.user_action.kind == ErrorReportParityTestData.EXPECTED_USER_ACTION_KIND

    async def test_wf_pipe_run_failure_threads_error_report_to_webhook_and_submitter(
        self,
        temporal_client: TemporalClient,
        mocker: MockerFixture,
        temporal_enabled: None,  # noqa: ARG002 - enables temporal.is_enabled for the duration
        failing_pipe_job: PipeJob,
    ) -> None:
        """The outer ``WfPipeRun`` wrap surfaces the inner classification on BOTH the webhook payload and the submitter-side error."""
        mocker.patch(
            ACT_LLM_GEN_TEXT_TARGET,
            new=mocker.AsyncMock(side_effect=ErrorReportParityTestData.make_failing_llm_error()),
        )

        captured_webhook_payloads: list[dict[str, Any]] = []
        mock_httpx_client = mocker.AsyncMock()
        mock_response = mocker.MagicMock()
        mock_response.raise_for_status = mocker.Mock()
        mock_httpx_client.__aenter__ = mocker.AsyncMock(return_value=mock_httpx_client)
        mock_httpx_client.__aexit__ = mocker.AsyncMock(return_value=False)

        def capture_post(url: str, **kwargs: Any) -> Any:  # noqa: ARG001
            captured_webhook_payloads.append(kwargs["json"])
            return mock_response

        mock_httpx_client.post = mocker.AsyncMock(side_effect=capture_post)
        mocker.patch("pipelex.pipe_run.delivery_executor.httpx.AsyncClient", return_value=mock_httpx_client)

        delivery_assignment = DeliveryAssignment(webhooks=[WebhookTarget(url="https://test.example.com/hook")])
        pipe_run_arg = PipeRunArg(pipe_job=failing_pipe_job, delivery_assignment=delivery_assignment).prepare_for_temporal()

        task_queue = f"q_wfrun_err_{uuid.uuid4().hex[:8]}"
        workflow_id = f"wf_wfrun_err_{uuid.uuid4().hex[:8]}"
        executor: WorkflowExecutor[PipeRunArg, PipeOutput] = WorkflowExecutor(
            temporal_client=temporal_client,
            task_queue=task_queue,
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            with pytest.raises(WorkflowExecutionError) as exc_info:
                await executor.execute_workflow(
                    workflow_class=WfPipeRun,
                    workflow_arg=pipe_run_arg,
                    workflow_id=workflow_id,
                )

        assert len(captured_webhook_payloads) == 1, (
            f"webhook should fire exactly once on the FAILED delivery path, got {len(captured_webhook_payloads)}"
        )
        payload = captured_webhook_payloads[0]
        assert payload["status"] == DeliveryStatus.FAILED
        assert "error" in payload, "FAILED delivery webhook must include the structured error report"
        error_dict = payload["error"]
        assert error_dict["error_type"] == "LLMCompletionError"
        assert error_dict["error_category"] == ErrorReportParityTestData.FAILURE_CATEGORY
        assert error_dict["retryable"] == ErrorReportParityTestData.EXPECTED_RETRYABLE
        assert error_dict["model"] == ErrorReportParityTestData.FAILURE_MODEL
        assert error_dict["provider"] == ErrorReportParityTestData.FAILURE_PROVIDER
        # LLMCompletionError auto-derives its title (no _declared_title) — CogtError's curated title doesn't leak through.
        assert error_dict["title"] == "Llm completion"
        assert error_dict["type_uri"] == "https://docs.pipelex.com/latest/errors/llm-completion-error/"
        assert error_dict["user_action"]["kind"] == ErrorReportParityTestData.EXPECTED_USER_ACTION_KIND

        submitter_error = exc_info.value
        assert submitter_error.error_report is not None
        submitter_report = submitter_error.to_error_report()
        assert submitter_report.error_category == ErrorReportParityTestData.FAILURE_CATEGORY
        assert submitter_report.retryable == ErrorReportParityTestData.EXPECTED_RETRYABLE
        assert submitter_report.model == ErrorReportParityTestData.FAILURE_MODEL
        assert submitter_report.provider == ErrorReportParityTestData.FAILURE_PROVIDER
        assert submitter_report.user_action is not None
        assert submitter_report.user_action.kind == ErrorReportParityTestData.EXPECTED_USER_ACTION_KIND

    async def test_wf_pipe_run_failure_without_delivery_assignment_surfaces_classification(
        self,
        temporal_client: TemporalClient,
        mocker: MockerFixture,
        temporal_enabled: None,  # noqa: ARG002 - enables temporal.is_enabled for the duration
        failing_pipe_job: PipeJob,
    ) -> None:
        """Submitter-side path still surfaces classification when no ``delivery_assignment`` is configured."""
        mocker.patch(
            ACT_LLM_GEN_TEXT_TARGET,
            new=mocker.AsyncMock(side_effect=ErrorReportParityTestData.make_failing_llm_error()),
        )

        pipe_run_arg = PipeRunArg(pipe_job=failing_pipe_job, delivery_assignment=None).prepare_for_temporal()

        task_queue = f"q_wfrun_err_nd_{uuid.uuid4().hex[:8]}"
        workflow_id = f"wf_wfrun_err_nd_{uuid.uuid4().hex[:8]}"
        executor: WorkflowExecutor[PipeRunArg, PipeOutput] = WorkflowExecutor(
            temporal_client=temporal_client,
            task_queue=task_queue,
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        async with get_task_manager().make_worker(temporal_client, task_queue=task_queue, is_not_sandboxed=True):
            with pytest.raises(WorkflowExecutionError) as exc_info:
                await executor.execute_workflow(
                    workflow_class=WfPipeRun,
                    workflow_arg=pipe_run_arg,
                    workflow_id=workflow_id,
                )

        submitter_error = exc_info.value
        assert submitter_error.error_report is not None
        submitter_report = submitter_error.to_error_report()
        assert submitter_report.error_category == ErrorReportParityTestData.FAILURE_CATEGORY
        assert submitter_report.retryable == ErrorReportParityTestData.EXPECTED_RETRYABLE
        assert submitter_report.model == ErrorReportParityTestData.FAILURE_MODEL
        assert submitter_report.provider == ErrorReportParityTestData.FAILURE_PROVIDER
        assert submitter_report.user_action is not None
        assert submitter_report.user_action.kind == ErrorReportParityTestData.EXPECTED_USER_ACTION_KIND
