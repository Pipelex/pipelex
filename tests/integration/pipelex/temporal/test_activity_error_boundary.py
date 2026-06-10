"""Integration test for the Temporal activity error boundary (Followup 5).

Drives a real activity through a real Temporal worker, makes its inner generate
call raise a real ``CogtError``, and asserts what ``TemporalError.from_app_error``
observes on the workflow side.

Each in-scope activity is decorated with ``@convert_pipelex_errors``, so a raised
``PipelexError`` becomes a ``TemporalError`` that packs ``to_error_report()`` into
``ApplicationError.details`` and derives ``non_retryable`` from the error's
``InferenceErrorCategory``. Without that boundary, Temporal's default failure
converter auto-wraps the raw error, ``from_app_error`` lands in its
``error_report is None`` fallback, and the category-aware retry decision never runs.

Two probe workflows exercise the boundary: one over an LLM activity
(``act_llm_gen_text``) and one over a non-LLM activity
(``act_extract_gen_extract_pages``), proving the wiring is not LLM-specific.
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
from pipelex.cogt.content_generation.assignment_models import ExtractAssignment, LLMAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.exceptions import CogtError, InferenceErrorCategory
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.hub import get_model_deck
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.temporal.tprl.temporal_error import TemporalError
from pipelex.temporal.tprl_content_generation.act_extract_generate import act_extract_gen_extract_pages
from pipelex.temporal.tprl_content_generation.act_llm_generate import act_llm_gen_text

ACTIVITY_FAILURE_MESSAGE = "simulated activity failure"


class ErrorBoundaryProbeResult(BaseModel):
    """What the workflow side observed after re-wrapping the activity failure.

    Returned (not re-raised) by the probe workflow so the test can assert on the
    payload that survived the activity → workflow boundary.
    """

    non_retryable: bool
    error_report: dict[str, Any] | None = None


def _probe_result_from_activity_error(exc: ActivityError, activity_name: str) -> ErrorBoundaryProbeResult:
    """Run the workflow-side bridge on an ``ActivityError`` and capture the conversion.

    Temporal wraps an activity failure's cause as an ``ApplicationError``; anything
    else (a timeout, a cancellation) means the probe never reached the bridge and
    is a hard test error.
    """
    cause = exc.cause
    if not isinstance(cause, ApplicationError):
        unexpected_cause_msg = f"{activity_name} should fail with an ApplicationError cause, got {type(cause).__name__}: {cause}"
        raise TypeError(unexpected_cause_msg) from exc
    temporal_error = TemporalError.from_app_error(exc=cause)
    return ErrorBoundaryProbeResult(
        non_retryable=temporal_error.non_retryable,
        error_report=temporal_error.error_report,
    )


@workflow.defn(name="wf_error_boundary_probe")
class WfErrorBoundaryProbe:
    """Executes the real ``act_llm_gen_text`` activity, expects it to fail, and reports the conversion.

    ``maximum_attempts=1`` on the activity retry policy is mandatory: a failure
    that is (wrongly) classified retryable would otherwise loop until the timeout
    and hang the test. The probe only cares about the first hop.
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
            return _probe_result_from_activity_error(exc=exc, activity_name="act_llm_gen_text")
        unreachable_msg = "act_llm_gen_text was expected to fail"
        raise AssertionError(unreachable_msg)


@workflow.defn(name="wf_extract_error_boundary_probe")
class WfExtractErrorBoundaryProbe:
    """Same probe over the non-LLM ``act_extract_gen_extract_pages`` activity.

    Proves the error boundary is wired on every in-scope activity, not just the
    LLM ones. See ``WfErrorBoundaryProbe`` for why ``maximum_attempts=1`` is set.
    """

    @workflow.run
    async def run(self, extract_assignment: ExtractAssignment) -> ErrorBoundaryProbeResult:
        try:
            await workflow.execute_activity(
                act_extract_gen_extract_pages,
                arg=extract_assignment,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except ActivityError as exc:
            return _probe_result_from_activity_error(exc=exc, activity_name="act_extract_gen_extract_pages")
        unreachable_msg = "act_extract_gen_extract_pages was expected to fail"
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
            cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE),
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
        else:
            # A category-less CogtError has no retryability signal — to_error_report()
            # drops the None-valued field, so the key is absent from the report.
            assert "retryable" not in result.error_report, "a category-less CogtError must carry no retryability signal in its report"

    async def test_real_non_llm_activity_failure_surfaces_error_report_on_workflow_side(
        self,
        temporal_client: TemporalClient,
        mocker: MockerFixture,
    ) -> None:
        """The boundary is wired on non-LLM activities too: a ``CogtError`` raised
        inside ``act_extract_gen_extract_pages`` must reach the workflow side as a
        ``TemporalError`` with a populated ``ErrorReport`` and category-aware
        ``non_retryable``.
        """
        raised_error = CogtError(ACTIVITY_FAILURE_MESSAGE, error_category=InferenceErrorCategory.CONFIGURATION)
        mocker.patch(
            "pipelex.temporal.tprl_content_generation.act_extract_generate.extract_gen_pages_and_store",
            new=mocker.AsyncMock(side_effect=raised_error),
        )

        extract_assignment = ExtractAssignment(
            job_metadata=JobMetadata(user_id="test", pipeline_run_id="test"),
            cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE),
            extract_handle="extract-handle-never-reached",
            extract_input=ExtractInput(document_uri="file://never-reached.pdf"),
            extract_job_params=ExtractJobParams.make_default_extract_job_params(),
            extract_job_config=ExtractJobConfig(),
        )

        task_queue = f"q_err_boundary_{uuid.uuid4().hex[:8]}"
        workflow_id = f"wf_err_boundary_{uuid.uuid4().hex[:8]}"

        async with Worker(
            temporal_client,
            task_queue=task_queue,
            workflows=[WfExtractErrorBoundaryProbe],
            activities=[act_extract_gen_extract_pages],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            result: ErrorBoundaryProbeResult = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                WfExtractErrorBoundaryProbe.run,
                arg=extract_assignment,
                id=workflow_id,
                task_queue=task_queue,
            )

        log.info(f"ErrorBoundaryProbeResult: {result}")

        assert result.non_retryable is True, "a CONFIGURATION CogtError must be non-retryable on the workflow side"
        assert result.error_report is not None, "the structured ErrorReport must survive the activity → workflow boundary"
        assert result.error_report["error_type"] == "CogtError"
        assert result.error_report["message"] == ACTIVITY_FAILURE_MESSAGE
        assert result.error_report["error_category"] == InferenceErrorCategory.CONFIGURATION
        assert result.error_report["retryable"] is False
