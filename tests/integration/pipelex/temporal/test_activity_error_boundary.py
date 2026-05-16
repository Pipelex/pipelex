"""RED integration test for the Temporal activity error boundary (Followup 5).

Drives the real ``act_llm_gen_text`` activity through a real Temporal worker,
makes its inner ``llm_gen_text`` raise a real ``CogtError``, and asserts what
``TemporalError.from_app_error`` observes on the workflow side.

Today this test FAILS: the activities raise raw ``CogtError`` and Temporal's
default failure converter auto-wraps them without packing ``to_error_report()``
into ``ApplicationError.details`` and without setting ``non_retryable``. So
``from_app_error`` lands in its ``error_report is None`` fallback branch and the
category-aware retry decision never runs. It turns GREEN once each activity
converts ``PipelexError`` to ``TemporalError`` at its boundary.
"""

import uuid
from datetime import timedelta
from typing import Any

import pytest
from pydantic import BaseModel
from pytest_mock import MockerFixture
from temporalio import workflow
from temporalio.client import Client as TemporalClient
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import LLMAssignment
from pipelex.cogt.exceptions import CogtError, InferenceErrorCategory
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.hub import get_model_deck
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.temporal.tprl.temporal_error import TemporalError
from pipelex.temporal.tprl_content_generation.act_llm_generate import act_llm_gen_text

ACTIVITY_FAILURE_MESSAGE = "simulated activity failure"


class ErrorBoundaryProbeResult(BaseModel):
    """What the workflow side observed after re-wrapping the activity failure.

    Returned (not re-raised) by the probe workflow so the test can assert on the
    payload that survived the activity → workflow boundary.
    """

    non_retryable: bool
    error_report: dict[str, Any] | None = None


@workflow.defn(name="wf_error_boundary_probe")
class WfErrorBoundaryProbe:
    """Executes one real activity, expects it to fail, and reports the conversion.

    ``maximum_attempts=1`` on the activity retry policy is mandatory: a failure
    that is (today, wrongly) classified retryable would otherwise loop until the
    timeout and hang the test. The probe only cares about the first hop.
    """

    @workflow.run
    async def run(self, llm_assignment: LLMAssignment) -> ErrorBoundaryProbeResult:
        try:
            await workflow.execute_activity(
                act_llm_gen_text,
                arg=llm_assignment,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except ActivityError as exc:
            if isinstance(exc.cause, ApplicationError):
                temporal_error = TemporalError.from_app_error(exc=exc.cause)
                return ErrorBoundaryProbeResult(
                    non_retryable=temporal_error.non_retryable,
                    error_report=temporal_error.error_report,
                )
            raise
        unreachable_msg = "act_llm_gen_text was expected to fail"
        raise AssertionError(unreachable_msg)


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestActivityErrorBoundary:
    @pytest.mark.parametrize(
        ("error_category", "expected_non_retryable"),
        [
            pytest.param(InferenceErrorCategory.CONFIGURATION, True, id="configuration-non-retryable"),
            pytest.param(InferenceErrorCategory.TRANSIENT, False, id="transient-retryable"),
            pytest.param(None, False, id="category-less-fallback"),
        ],
    )
    async def test_real_activity_failure_surfaces_error_report_on_workflow_side(
        self,
        temporal_client: TemporalClient,
        mocker: MockerFixture,
        error_category: InferenceErrorCategory | None,
        expected_non_retryable: bool,
    ) -> None:
        """A real ``CogtError`` raised inside ``act_llm_gen_text`` must reach the
        workflow side as a ``TemporalError`` carrying a populated ``ErrorReport``
        and the category-aware ``non_retryable`` flag.
        """
        # Make the activity's inner generate call raise a real CogtError. The
        # worker runs in-process, so patching the activity module's imported
        # name reaches the activity when it executes.
        raised_error = CogtError(ACTIVITY_FAILURE_MESSAGE, error_category=error_category)
        mocker.patch(
            "pipelex.temporal.tprl_content_generation.act_llm_generate.llm_gen_text",
            new=mocker.AsyncMock(side_effect=raised_error),
        )

        llm_assignment = LLMAssignment(
            job_metadata=JobMetadata(user_id="test", pipeline_run_id="test"),
            llm_setting=get_model_deck().get_llm_setting(llm_choice="$testing-text"),
            llm_prompt=LLMPrompt(user_text="never reaches the model — llm_gen_text is mocked"),
        )

        task_queue = f"q_err_boundary_{uuid.uuid4().hex[:8]}"
        workflow_id = f"wf_err_boundary_{uuid.uuid4().hex[:8]}"

        async with Worker(
            temporal_client,
            task_queue=task_queue,
            workflows=[WfErrorBoundaryProbe],
            activities=[act_llm_gen_text],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            result: ErrorBoundaryProbeResult = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                WfErrorBoundaryProbe.run,
                arg=llm_assignment,
                id=workflow_id,
                task_queue=task_queue,
            )

        log.info(f"ErrorBoundaryProbeResult: {result}")

        assert result.non_retryable is expected_non_retryable, (
            f"non_retryable should be {expected_non_retryable} for category={error_category}, got {result.non_retryable}"
        )
        assert result.error_report is not None, "the structured ErrorReport must survive the activity → workflow boundary"
        assert result.error_report["error_type"] == "CogtError"
        assert result.error_report["message"] == ACTIVITY_FAILURE_MESSAGE
        if error_category is not None:
            assert result.error_report["error_category"] == error_category
            assert result.error_report["retryable"] is (not expected_non_retryable)
