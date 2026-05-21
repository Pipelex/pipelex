import json

import pytest
from pydantic import ValidationError

from pipelex.base_exceptions import ErrorReport, PipelexError
from pipelex.cogt.exceptions import (
    CogtError,
    ExtractJobFailureError,
    ExtractModelNotFoundError,
    ImgGenGenerationError,
    ImgGenModelNotFoundError,
    InferenceBackendCredentialsError,
    InferenceBackendCredentialsErrorType,
    InferenceErrorCategory,
    LLMCapabilityError,
    LLMCompletionError,
    LLMModelNotFoundError,
    ModelNotFoundError,
    ModelWaterfallError,
    SearchJobFailureError,
    SearchModelNotFoundError,
)
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserAction, UserActionKind
from pipelex.cogt.inference.provider_name import ProviderName
from tests.unit.pipelex.cogt.test_data import ExceptionTestData


class TestErrorCategoryInfrastructure:
    """Tests for the InferenceErrorCategory enum, CogtError fields, and to_error_report()."""

    # --- InferenceErrorCategory enum ---

    @pytest.mark.parametrize(
        ("_topic", "category", "expected_retryable"),
        ExceptionTestData.CATEGORY_RETRYABLE_CASES,
    )
    def test_is_retryable(
        self,
        _topic: str,
        category: InferenceErrorCategory,
        expected_retryable: bool,
    ) -> None:
        """is_retryable returns True only for TRANSIENT."""
        assert category.is_retryable == expected_retryable

    # --- error_category field ---

    def test_cogt_error_default_category_is_none(self) -> None:
        """CogtError with no category argument defaults to None."""
        err = CogtError("something broke")
        assert err.error_category is None

    def test_cogt_error_instance_category_override(self) -> None:
        """CogtError accepts error_category at construction time."""
        err = CogtError("transient issue", error_category=InferenceErrorCategory.TRANSIENT)
        assert err.error_category is InferenceErrorCategory.TRANSIENT

    def test_subclass_class_level_category(self) -> None:
        """Subclasses with class-level category inherit it without passing to __init__."""
        err = LLMCapabilityError("model does not support vision")
        assert err.error_category is InferenceErrorCategory.CONFIGURATION

    def test_subclass_with_custom_init_preserves_category(self) -> None:
        """Subclasses with custom __init__ still get their class-level category."""
        err = LLMModelNotFoundError(message="not found", model_handle="gpt-4")
        assert err.error_category is InferenceErrorCategory.CONFIGURATION
        assert err.model_handle == "gpt-4"

    def test_model_waterfall_error_preserves_class_level_category(self) -> None:
        """ModelWaterfallError forwards only message + model_handle to ModelNotFoundError.__init__;
        the new optional kwargs default to None and must not clobber the class-level
        error_category = CONFIGURATION.
        """
        err = ModelWaterfallError(message="waterfall exhausted", model_handle="gpt-4", fallback_list=["gpt-3.5"])
        assert err.error_category is InferenceErrorCategory.CONFIGURATION
        assert err.model_handle == "gpt-4"
        assert err.fallback_list == ["gpt-3.5"]
        assert err.user_action is None
        assert err.provider_metadata is None

    def test_llm_model_not_found_error_carries_new_kwargs(self) -> None:
        """LLMModelNotFoundError accepts user_action and provider_metadata via the widened
        ModelNotFoundError.__init__, so worker-side categorization can attach SDK metadata.
        """
        metadata = ProviderErrorMetadata(provider=ProviderName.OPENAI, sdk_exception_type="NotFoundError", status_code=404)
        user_action = UserAction(kind=UserActionKind.CHANGE_MODEL, detail="pick another model")
        err = LLMModelNotFoundError(
            message="model gpt-99 not found",
            model_handle="gpt-99",
            user_action=user_action,
            provider_metadata=metadata,
        )
        assert err.error_category is InferenceErrorCategory.CONFIGURATION
        assert err.model_handle == "gpt-99"
        assert err.user_action is user_action
        assert err.provider_metadata is metadata

    def test_instance_override_beats_class_default(self) -> None:
        """Per-instance category overrides the class-level default."""
        err = LLMCompletionError("timeout", error_category=InferenceErrorCategory.TRANSIENT)
        assert err.error_category is InferenceErrorCategory.TRANSIENT

    # --- user_action field ---

    def test_user_action_default_none(self) -> None:
        """user_action defaults to None."""
        err = CogtError("something broke")
        assert err.user_action is None

    def test_user_action_instance_set(self) -> None:
        """user_action can be set at construction."""
        err = CogtError(
            "bad config",
            user_action=UserAction(kind=UserActionKind.CHECK_CREDENTIALS, detail="Check your API key"),
        )
        assert err.user_action is not None
        assert err.user_action.kind is UserActionKind.CHECK_CREDENTIALS
        assert err.user_action.detail == "Check your API key"

    def test_user_action_class_level(self) -> None:
        """Subclass with class-level user_action inherits it."""
        err = InferenceBackendCredentialsError(
            credentials_error_type=InferenceBackendCredentialsErrorType.VAR_NOT_FOUND,
            backend_name="openai",
            message="key missing",
            key_name="OPENAI_API_KEY",
        )
        assert err.user_action is not None
        assert err.user_action.kind is UserActionKind.CHECK_CREDENTIALS
        assert err.user_action.detail == "Check that the required API key environment variable is set"

    # --- to_error_report() ---

    def test_to_error_report_pipelex_error_minimal(self) -> None:
        """PipelexError.to_error_report returns an ErrorReport with error_type and message."""
        err = PipelexError("basic error")
        report = err.to_error_report()
        assert report.error_type == "PipelexError"
        assert report.message == "basic error"
        assert report.error_category is None
        assert report.retryable is None

    def test_to_error_report_cogt_error_no_category(self) -> None:
        """CogtError report has None for optional fields when not set."""
        err = CogtError("plain error")
        report = err.to_error_report()
        assert report.error_type == "CogtError"
        assert report.message == "plain error"
        assert report.error_category is None
        assert report.retryable is None
        assert report.user_action is None
        assert report.model is None
        assert report.provider is None

    def test_to_error_report_with_category(self) -> None:
        """CogtError report includes category and retryable when set."""
        err = CogtError("oops", error_category=InferenceErrorCategory.CONTENT)
        report = err.to_error_report()
        assert report.error_category == "content"
        assert report.retryable is False

    def test_to_error_report_with_all_cogt_fields(self) -> None:
        """Report includes user_action when set."""
        err = CogtError(
            "oops",
            error_category=InferenceErrorCategory.TRANSIENT,
            user_action=UserAction(kind=UserActionKind.WAIT_AND_RETRY, detail="Retry in a moment"),
        )
        report = err.to_error_report()
        assert report.error_category == "transient"
        assert report.retryable is True
        assert report.user_action is not None
        assert report.user_action.kind is UserActionKind.WAIT_AND_RETRY
        assert report.user_action.detail == "Retry in a moment"

    def test_to_error_report_with_model_handle(self) -> None:
        """Report includes model field for errors with model_handle."""
        err = LLMModelNotFoundError(message="missing", model_handle="gpt-4o")
        report = err.to_error_report()
        assert report.model == "gpt-4o"
        assert report.error_category == "configuration"

    def test_to_error_report_with_provider(self) -> None:
        """Report includes provider field for errors with backend_name."""
        err = InferenceBackendCredentialsError(
            credentials_error_type=InferenceBackendCredentialsErrorType.VAR_NOT_FOUND,
            backend_name="openai",
            message="key missing",
            key_name="OPENAI_API_KEY",
        )
        report = err.to_error_report()
        assert report.provider == "openai"
        assert report.error_category == "configuration"

    def test_to_error_report_to_dict_omits_none(self) -> None:
        """to_dict() omits None-valued fields."""
        err = CogtError("plain error")
        report_dict = err.to_error_report().to_dict()
        assert "error_category" not in report_dict
        assert "retryable" not in report_dict
        assert "user_action" not in report_dict
        assert "model" not in report_dict
        assert "provider" not in report_dict
        assert report_dict == {
            "error_type": "CogtError",
            "message": "plain error",
            "title": "AI inference failed",
            "type_uri": "https://docs.pipelex.com/latest/errors/cogt-error/",
        }

    def test_to_error_report_to_dict_json_serializable(self) -> None:
        """to_dict() output can be serialized to JSON."""
        err = LLMModelNotFoundError(message="not found", model_handle="gpt-4o")
        report_dict = err.to_error_report().to_dict()
        serialized = json.dumps(report_dict)
        deserialized = json.loads(serialized)
        assert deserialized == report_dict

    def test_error_report_is_frozen(self) -> None:
        """ErrorReport is immutable."""
        report = ErrorReport(
            error_type="CogtError",
            message="test",
            title="AI inference failed",
            type_uri="https://docs.pipelex.com/latest/errors/cogt-error/",
        )
        with pytest.raises(ValidationError):
            report.message = "mutated"  # type: ignore[misc]

    def test_from_exc_chain_preserved(self) -> None:
        """Exception cause chain is preserved with from exc."""
        original = ValueError("original error")
        msg = "wrapped"
        with pytest.raises(CogtError) as exc_info:
            raise CogtError(msg, error_category=InferenceErrorCategory.TRANSIENT) from original
        assert exc_info.value.__cause__ is original
        report = exc_info.value.to_error_report()
        assert report.error_category == "transient"

    # --- ModelNotFoundError hierarchy: the load-bearing reroute invariant ---

    def test_llm_model_not_found_is_model_not_found_not_completion_error(self) -> None:
        """LLMModelNotFoundError is a ModelNotFoundError, NOT an LLMCompletionError.

        The whole provider-404 reroute depends on this: a 404 must escape PipeLLM's
        `except LLMCompletionError` and reach `except ModelNotFoundError` in PipeOperator.
        Reparenting LLMModelNotFoundError under LLMCompletionError would silently break it.
        """
        assert issubclass(LLMModelNotFoundError, ModelNotFoundError)
        assert not issubclass(LLMModelNotFoundError, LLMCompletionError)

    def test_img_gen_model_not_found_is_model_not_found_not_generation_error(self) -> None:
        """ImgGenModelNotFoundError is a ModelNotFoundError, NOT an ImgGenGenerationError — same reroute invariant."""
        assert issubclass(ImgGenModelNotFoundError, ModelNotFoundError)
        assert not issubclass(ImgGenModelNotFoundError, ImgGenGenerationError)

    def test_extract_model_not_found_is_model_not_found_not_job_failure_error(self) -> None:
        """ExtractModelNotFoundError is a ModelNotFoundError, NOT an ExtractJobFailureError — same reroute invariant."""
        assert issubclass(ExtractModelNotFoundError, ModelNotFoundError)
        assert not issubclass(ExtractModelNotFoundError, ExtractJobFailureError)

    def test_search_model_not_found_is_model_not_found_not_job_failure_error(self) -> None:
        """SearchModelNotFoundError is a ModelNotFoundError, NOT a SearchJobFailureError — same reroute invariant."""
        assert issubclass(SearchModelNotFoundError, ModelNotFoundError)
        assert not issubclass(SearchModelNotFoundError, SearchJobFailureError)
