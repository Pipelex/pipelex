import json

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
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
    find_inference_error_category_in_chain,
)
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserAction, UserActionKind
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.errors.problem import PipelexProblem, ProblemView
from tests.unit.pipelex.cogt.test_data import ExceptionTestData


class TestErrorCategoryInfrastructure:
    """Tests for the InferenceErrorCategory enum, CogtError fields, and to_problem()."""

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

    # --- to_problem() ---

    def test_to_problem_pipelex_error_minimal(self) -> None:
        """A bare PipelexError reports the fallback code and its verdict, its class and message for the operator alone."""
        err = PipelexError("basic error")
        problem = err.to_problem(view=ProblemView.OPERATOR)
        assert problem.code == CoreCode.RUNTIME_UNEXPECTED
        assert problem.is_retryable is False
        assert problem.diagnostics is not None
        assert problem.diagnostics.error_class == "PipelexError"
        assert problem.diagnostics.message == "basic error"
        assert find_inference_error_category_in_chain(err) is None

    def test_to_problem_cogt_error_no_category(self) -> None:
        """A failure with no category and no cause reports its class's fallback code, and no advice, model or provider."""
        err = LLMCompletionError("plain error")
        problem = err.to_problem(view=ProblemView.OPERATOR)
        assert problem.code == CoreCode.RUNTIME_UNEXPECTED
        assert problem.is_retryable is False
        assert problem.diagnostics is not None
        assert problem.diagnostics.error_class == "LLMCompletionError"
        assert problem.diagnostics.message == "plain error"
        assert problem.diagnostics.model is None
        assert problem.diagnostics.provider is None
        assert find_inference_error_category_in_chain(err) is None
        assert err.advised_action() is None

    def test_to_problem_with_category(self) -> None:
        """The category stays on the chain, and a content failure with no code keeps its class's fallback."""
        err = LLMCompletionError("oops", error_category=InferenceErrorCategory.CONTENT)
        problem = err.to_problem(view=ProblemView.CALLER)
        assert find_inference_error_category_in_chain(err) == InferenceErrorCategory.CONTENT
        assert problem.code == CoreCode.RUNTIME_UNEXPECTED
        assert problem.is_retryable is False

    def test_to_problem_with_all_cogt_fields(self) -> None:
        """The advice rides the error, never the problem, and a transient failure with no code reports a code that invites a retry."""
        err = LLMCompletionError(
            "oops",
            error_category=InferenceErrorCategory.TRANSIENT,
            user_action=UserAction(kind=UserActionKind.WAIT_AND_RETRY, detail="Retry in a moment"),
        )
        problem = err.to_problem(view=ProblemView.OPERATOR)
        assert find_inference_error_category_in_chain(err) == InferenceErrorCategory.TRANSIENT
        assert problem.code == CoreCode.PROVIDER_UNAVAILABLE
        assert problem.is_retryable is True
        advice = err.advised_action()
        assert advice is not None
        assert advice.kind is UserActionKind.WAIT_AND_RETRY
        assert advice.detail == "Retry in a moment"
        assert "Retry in a moment" not in json.dumps(problem.to_wire())

    def test_to_problem_with_model_handle(self) -> None:
        """The operator's diagnostics name the model of an error carrying a model_handle."""
        err = LLMModelNotFoundError(message="missing", model_handle="gpt-4o")
        problem = err.to_problem(view=ProblemView.OPERATOR)
        assert problem.diagnostics is not None
        assert problem.diagnostics.model == "gpt-4o"
        assert find_inference_error_category_in_chain(err) == InferenceErrorCategory.CONFIGURATION

    def test_to_problem_with_provider(self) -> None:
        """The operator's diagnostics name the provider of an error carrying a backend_name, which the caller never reads."""
        err = InferenceBackendCredentialsError(
            credentials_error_type=InferenceBackendCredentialsErrorType.VAR_NOT_FOUND,
            backend_name="openai",
            message="key missing",
            key_name="OPENAI_API_KEY",
        )
        problem = err.to_problem(view=ProblemView.OPERATOR)
        assert problem.diagnostics is not None
        assert problem.diagnostics.provider is not None
        assert problem.diagnostics.provider.name == "openai"
        assert find_inference_error_category_in_chain(err) == InferenceErrorCategory.CONFIGURATION
        assert err.to_problem(view=ProblemView.CALLER).diagnostics is None

    def test_to_problem_to_wire_omits_none(self) -> None:
        """to_wire() omits every member that holds no value, and the caller's view carries no diagnostics."""
        err = LLMCompletionError("plain error")
        assert err.to_problem(view=ProblemView.CALLER).to_wire() == {
            "type": "https://mthds.ai/errors/runtime.unexpected",
            "title": "An unexpected error occurred",
            "detail": "The runtime met an unexpected error.",
            "code": "runtime.unexpected",
            "domain": "runtime",
            "retry": "no",
            "next_step": {"kind": "report", "detail": "Report this to whoever runs the runtime."},
        }
        operator_wire = err.to_problem(view=ProblemView.OPERATOR).to_wire()
        assert operator_wire["diagnostics"]["error_class"] == "LLMCompletionError"
        assert operator_wire["diagnostics"]["message"] == "plain error"
        assert "model" not in operator_wire["diagnostics"]
        assert "provider" not in operator_wire["diagnostics"]

    def test_to_problem_to_wire_json_serializable(self) -> None:
        """to_wire() output can be serialized to JSON and read back as the same problem."""
        err = LLMModelNotFoundError(message="not found", model_handle="gpt-4o")
        problem_wire = err.to_problem(view=ProblemView.OPERATOR).to_wire()
        deserialized = json.loads(json.dumps(problem_wire))
        assert deserialized == problem_wire
        assert PipelexProblem.model_validate(deserialized).to_wire() == problem_wire

    def test_from_exc_chain_preserved(self) -> None:
        """Exception cause chain is preserved with from exc."""
        original = ValueError("original error")
        msg = "wrapped"
        with pytest.raises(CogtError) as exc_info:
            raise LLMCompletionError(msg, error_category=InferenceErrorCategory.TRANSIENT) from original
        assert exc_info.value.__cause__ is original
        assert find_inference_error_category_in_chain(exc_info.value) == InferenceErrorCategory.TRANSIENT
        assert exc_info.value.to_problem(view=ProblemView.CALLER).is_retryable is True

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
