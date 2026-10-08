"""Tests for ``render_inference_error`` — the provider-blind Render step.

Builds synthetic envelopes + classifications and asserts the rendered
``CogtError`` subclass, its category, structured ``UserAction``, and metadata.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from pipelex.cogt.exceptions import (
    CogtError,
    ExtractJobFailureError,
    ExtractModelNotFoundError,
    ImgGenGenerationError,
    ImgGenModelNotFoundError,
    InferenceErrorCategory,
    LLMCompletionError,
    LLMModelNotFoundError,
    SearchJobFailureError,
    SearchModelNotFoundError,
)
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserActionKind
from pipelex.cogt.inference.error_classify import ClassificationResult
from pipelex.cogt.inference.error_render import InferenceErrorFamily, render_inference_error
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.system.pipe_run_mode import PipeRunMode


class _TestCases:
    # (topic, family, expected_failure_class, expected_not_found_class)
    FAMILIES: ClassVar[list[tuple[str, InferenceErrorFamily, type[CogtError], type[CogtError]]]] = [
        ("llm", InferenceErrorFamily.LLM, LLMCompletionError, LLMModelNotFoundError),
        ("img_gen", InferenceErrorFamily.IMG_GEN, ImgGenGenerationError, ImgGenModelNotFoundError),
        ("extract", InferenceErrorFamily.EXTRACT, ExtractJobFailureError, ExtractModelNotFoundError),
        ("search", InferenceErrorFamily.SEARCH, SearchJobFailureError, SearchModelNotFoundError),
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
        )

        rendered = render_inference_error(
            metadata=metadata,
            classification=classification,
            family=family,
            model_desc="gpt-fake",
            model_handle="fake-handle",
        )

        assert type(rendered) is expected_failure_class
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
        assert rendered.error_category == InferenceErrorCategory.CONFIGURATION
        assert rendered.model_handle == "fake-handle"
        assert rendered.provider_metadata is metadata

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

    @pytest.mark.parametrize(
        ("retry_after_seconds", "expected_detail"),
        [
            pytest.param(None, "Transient provider error — wait a moment, then run it again.", id="no_retry_after"),
            pytest.param(12.0, "Transient provider error — wait at least 12s, then run it again.", id="retry_after"),
        ],
    )
    def test_failed_run_report_says_to_wait_then_run_again(self, retry_after_seconds: float | None, expected_detail: str) -> None:
        """The advice a failed run's report carries for a transient inference error.

        The report is read once the run has failed and every automatic retry is spent, so the
        advice says what the reader can do, and never that the system will retry.
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

        report_payload = failed_run.to_error_report().to_dict()

        assert report_payload["user_action"] == {"kind": "wait_and_retry", "detail": expected_detail}
        assert "automatically" not in report_payload["user_action"]["detail"]
