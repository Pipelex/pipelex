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

    def test_retry_after_seconds_surfaced_in_detail(self) -> None:
        metadata = ProviderErrorMetadata(
            provider=ProviderName.OPENAI,
            sdk_exception_type="RateLimitError",
            message="Rate limited",
            status_code=429,
            retry_after_seconds=12.0,
        )
        classification = ClassificationResult(
            category=InferenceErrorCategory.TRANSIENT,
            user_action_kind=UserActionKind.WAIT_AND_RETRY,
        )

        rendered = render_inference_error(
            metadata=metadata,
            classification=classification,
            family=InferenceErrorFamily.LLM,
            model_desc="gpt-fake",
            model_handle="fake-handle",
        )

        assert rendered.user_action is not None
        assert "12s" in rendered.user_action.detail
