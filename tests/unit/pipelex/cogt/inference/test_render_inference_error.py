"""Tests for ``render_inference_error`` — the provider-blind Render step.

Builds synthetic envelopes + classifications and asserts the rendered
``CogtError`` subclass, its category, structured ``UserAction``, and metadata.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pytest
from mthds.protocol.problem.registry import CoreCode, StepKind

from pipelex.cogt.exceptions import (
    INFERENCE_FAILURE_CODES,
    CogtError,
    ExtractJobFailureError,
    ExtractModelNotFoundError,
    ImgGenGenerationError,
    ImgGenModelNotFoundError,
    InferenceErrorCategory,
    JudgmentJobFailureError,
    JudgmentModelNotFoundError,
    LLMCompletionError,
    LLMModelNotFoundError,
    SearchJobFailureError,
    SearchModelNotFoundError,
)
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserActionKind
from pipelex.cogt.inference.error_classify import ClassificationResult, InferenceErrorFamily
from pipelex.cogt.inference.error_render import _FAMILY_MODEL_TYPES, render_inference_error  # pyright: ignore[reportPrivateUsage]
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.errors.problem import ProblemView
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.system.pipe_run_mode import PipeRunMode

if TYPE_CHECKING:
    from pipelex.errors.error_codes import ErrorCode


class _TestCases:
    # (topic, family, expected_failure_class, expected_not_found_class)
    FAMILIES: ClassVar[list[tuple[str, InferenceErrorFamily, type[CogtError], type[CogtError]]]] = [
        ("llm", InferenceErrorFamily.LLM, LLMCompletionError, LLMModelNotFoundError),
        ("img_gen", InferenceErrorFamily.IMG_GEN, ImgGenGenerationError, ImgGenModelNotFoundError),
        ("extract", InferenceErrorFamily.EXTRACT, ExtractJobFailureError, ExtractModelNotFoundError),
        ("search", InferenceErrorFamily.SEARCH, SearchJobFailureError, SearchModelNotFoundError),
        ("judgment", InferenceErrorFamily.JUDGMENT, JudgmentJobFailureError, JudgmentModelNotFoundError),
    ]


def _metadata(status_code: int | None = 500) -> ProviderErrorMetadata:
    return ProviderErrorMetadata(
        provider=ProviderName.OPENAI,
        sdk_exception_type="InternalServerError",
        message="Internal server error",
        status_code=status_code,
    )


class TestRenderInferenceError:
    @pytest.mark.parametrize(
        ("_topic", "family", "expected_failure_class", "_expected_not_found_class"),
        _TestCases.FAMILIES,
    )
    def test_renders_failure_class_per_family(
        self,
        _topic: str,
        family: InferenceErrorFamily,
        expected_failure_class: type[CogtError],
        _expected_not_found_class: type[CogtError],
    ) -> None:
        metadata = _metadata()
        classification = ClassificationResult(
            category=InferenceErrorCategory.TRANSIENT,
            user_action_kind=UserActionKind.WAIT_AND_RETRY,
            error_code=CoreCode.PROVIDER_FAILED,
        )

        rendered = render_inference_error(
            metadata=metadata,
            classification=classification,
            family=family,
            model_desc="gpt-fake",
            model_handle="fake-handle",
        )

        assert type(rendered) is expected_failure_class
        assert rendered.resolve_error_code() == CoreCode.PROVIDER_FAILED
        assert rendered.error_category == InferenceErrorCategory.TRANSIENT
        assert rendered.user_action is not None
        assert rendered.user_action.kind == UserActionKind.WAIT_AND_RETRY
        assert rendered.provider_metadata is metadata
        assert "gpt-fake" in rendered.message

    @pytest.mark.parametrize(
        ("_topic", "family", "_expected_failure_class", "expected_not_found_class"),
        _TestCases.FAMILIES,
    )
    def test_renders_model_not_found_class_per_family(
        self,
        _topic: str,
        family: InferenceErrorFamily,
        _expected_failure_class: type[CogtError],
        expected_not_found_class: type[CogtError],
    ) -> None:
        metadata = _metadata(status_code=404)
        classification = ClassificationResult(
            category=InferenceErrorCategory.CONFIGURATION,
            user_action_kind=UserActionKind.CHANGE_MODEL,
            error_code=CoreCode.MODEL_UNAVAILABLE,
            is_model_not_found=True,
        )

        rendered = render_inference_error(
            metadata=metadata,
            classification=classification,
            family=family,
            model_desc="gpt-fake",
            model_handle="fake-handle",
        )

        assert type(rendered) is expected_not_found_class
        assert rendered.resolve_error_code() == CoreCode.MODEL_UNAVAILABLE
        assert rendered.error_category == InferenceErrorCategory.CONFIGURATION
        assert rendered.model_handle == "fake-handle"
        assert rendered.provider_metadata is metadata
        # The provider does not know the model the deck resolved, which the problem names with the family's kind of model.
        caller = rendered.to_problem(view=ProblemView.CALLER)
        assert caller.params is not None
        assert caller.params.as_wire() == {"model": "fake-handle", "model_type": _FAMILY_MODEL_TYPES[family], "reason": "unknown_at_provider"}

    def test_content_policy_detail_when_violation_present(self) -> None:
        metadata = ProviderErrorMetadata(
            provider=ProviderName.OPENAI,
            sdk_exception_type="BadRequestError",
            message="Request blocked by safety system",
            status_code=400,
        )
        classification = ClassificationResult(
            category=InferenceErrorCategory.CONTENT,
            user_action_kind=UserActionKind.CHANGE_INPUT,
            error_code=CoreCode.MODEL_CONTENT_REFUSED,
        )

        rendered = render_inference_error(
            metadata=metadata,
            classification=classification,
            family=InferenceErrorFamily.LLM,
            model_desc="gpt-fake",
            model_handle="fake-handle",
        )

        assert rendered.user_action is not None
        assert "safety filters" in rendered.user_action.detail

    @pytest.mark.builds_problems_without_required_params(
        reason="the rendered failure is built below the worker, whose enrichment names the model and the provider"
    )
    @pytest.mark.parametrize(
        ("retry_after_seconds", "expected_detail"),
        [
            pytest.param(None, "Transient provider error — wait a moment, then run it again.", id="no_retry_after"),
            pytest.param(12.0, "Transient provider error — wait at least 12s, then run it again.", id="retry_after"),
            pytest.param(12.4, "Transient provider error — wait at least 13s, then run it again.", id="retry_after_rounded_up"),
            pytest.param(0.0, "Transient provider error — wait a moment, then run it again.", id="retry_after_zero"),
        ],
    )
    def test_failed_run_advice_says_to_wait_then_run_again(self, retry_after_seconds: float | None, expected_detail: str) -> None:
        """The advice a failed run carries for a transient inference error.

        The advice is read once the run has failed and every automatic retry is spent, so it
        says what the reader can do, and never that the system will retry.
        """
        metadata = ProviderErrorMetadata(
            provider=ProviderName.OPENAI,
            sdk_exception_type="RateLimitError",
            message="Rate limited",
            status_code=429,
            retry_after_seconds=retry_after_seconds,
        )
        classification = ClassificationResult(
            category=InferenceErrorCategory.TRANSIENT,
            user_action_kind=UserActionKind.WAIT_AND_RETRY,
            error_code=CoreCode.PROVIDER_RATE_LIMITED,
        )
        root_fault = render_inference_error(
            metadata=metadata,
            classification=classification,
            family=InferenceErrorFamily.LLM,
            model_desc="gpt-fake",
            model_handle="fake-handle",
        )
        # Wrapped as the runner wraps it: located at the failing pipe, then reported as the run's failure.
        located = PipeRouterError.make_located(
            failure=root_fault,
            run_mode=PipeRunMode.LIVE,
            pipe_code="summarize",
            output_name=None,
            pipe_stack=["flow", "summarize"],
        )
        located.__cause__ = root_fault
        failed_run = PipelineExecutionError.make_for_run_failure(
            failure=located,
            run_mode=PipeRunMode.LIVE,
            entry_pipe_code="flow",
            output_name=None,
        )
        failed_run.__cause__ = located

        advice = failed_run.advised_action()
        assert advice is not None
        assert advice.kind == UserActionKind.WAIT_AND_RETRY
        assert advice.detail == expected_detail
        assert "automatically" not in advice.detail
        caller = failed_run.to_problem(view=ProblemView.CALLER)
        # The caller's problem invites the wait the provider asked for, as a member, never as advice.
        assert caller.code == CoreCode.PROVIDER_RATE_LIMITED
        assert caller.is_retryable is True
        assert caller.next_step.kind == StepKind.WAIT
        assert caller.retry_after == retry_after_seconds

    @pytest.mark.parametrize("error_code", INFERENCE_FAILURE_CODES, ids=str)
    @pytest.mark.parametrize(
        ("_topic", "family", "expected_failure_class", "_expected_not_found_class"),
        _TestCases.FAMILIES,
    )
    def test_every_classified_code_renders_for_every_family(
        self,
        _topic: str,
        family: InferenceErrorFamily,
        expected_failure_class: type[CogtError],
        _expected_not_found_class: type[CogtError],
        error_code: ErrorCode,
    ) -> None:
        """Each family's failure class declares every code a classification may carry, so the render never refuses one."""
        classification = ClassificationResult(
            category=InferenceErrorCategory.UNKNOWN,
            user_action_kind=UserActionKind.CONTACT_SUPPORT,
            error_code=error_code,
        )

        rendered = render_inference_error(
            metadata=_metadata(),
            classification=classification,
            family=family,
            model_desc="gpt-fake",
            model_handle="fake-handle",
        )

        assert type(rendered) is expected_failure_class
        assert rendered.resolve_error_code() == error_code

    def test_an_outcome_nobody_knows_is_not_advised_to_be_run_again_blind(self) -> None:
        """An image generation that may have run is checked for before it is repeated, whatever the kind says."""
        classification = ClassificationResult(
            category=InferenceErrorCategory.AMBIGUOUS,
            user_action_kind=UserActionKind.WAIT_AND_RETRY,
            error_code=CoreCode.PROVIDER_OUTCOME_UNKNOWN,
        )

        rendered = render_inference_error(
            metadata=_metadata(),
            classification=classification,
            family=InferenceErrorFamily.IMG_GEN,
            model_desc="gpt-image-fake",
            model_handle="fake-handle",
        )

        assert type(rendered) is ImgGenGenerationError
        assert rendered.resolve_error_code() == CoreCode.PROVIDER_OUTCOME_UNKNOWN
        assert rendered.user_action is not None
        assert "check for one before running it again" in rendered.user_action.detail
