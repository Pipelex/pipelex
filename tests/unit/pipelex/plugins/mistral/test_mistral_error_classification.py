"""Tests for ``classify_mistral_sdk_error``.

The classifier maps a Mistral SDK exception (or a raw ``httpx`` transport
error) to a categorized pipelex error, or ``None`` for an unrecognized type.
Verifies the error category, the user-action kind, and the
``LLMModelNotFoundError`` specialization for a 404.
"""

from __future__ import annotations

import httpx
import pytest
from mistralai import MistralError

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError, LLMModelNotFoundError
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.plugins.mistral.mistral_error_classification import classify_mistral_sdk_error

_MODEL_DESC = "test-model-desc"
_MODEL_ID = "mistral-test-id"
_MODEL_HANDLE = "mistral-test"


def _mistral_error(status_code: int, message: str) -> MistralError:
    request = httpx.Request("POST", "https://api.mistral.ai/v1/chat/completions")
    return MistralError(message, raw_response=httpx.Response(status_code=status_code, request=request))


def _classify(sdk_exc: BaseException) -> LLMCompletionError | LLMModelNotFoundError | None:
    return classify_mistral_sdk_error(
        sdk_exc=sdk_exc,
        model_desc=_MODEL_DESC,
        model_id=_MODEL_ID,
        model_handle=_MODEL_HANDLE,
    )


class TestClassifyMistralSdkError:
    """``classify_mistral_sdk_error`` maps every recognized SDK exception to the right category."""

    @pytest.mark.parametrize(
        ("_topic", "sdk_exc", "expected_category", "expected_action_kind"),
        [
            (
                "transport_connect_error",
                httpx.ConnectError("Connection refused"),
                InferenceErrorCategory.TRANSIENT,
                UserActionKind.WAIT_AND_RETRY,
            ),
            (
                "transport_read_timeout",
                httpx.ReadTimeout("Read timed out"),
                InferenceErrorCategory.TRANSIENT,
                UserActionKind.WAIT_AND_RETRY,
            ),
            (
                "payment_required_402",
                _mistral_error(402, "Payment required: insufficient credits"),
                InferenceErrorCategory.CAPACITY,
                UserActionKind.CHECK_BILLING,
            ),
            (
                "rate_limit_quota_429",
                _mistral_error(429, "Rate limit reached: your account quota has been exceeded"),
                InferenceErrorCategory.CAPACITY,
                UserActionKind.CHECK_BILLING,
            ),
            (
                "auth_error_401",
                _mistral_error(401, "Invalid API key provided"),
                InferenceErrorCategory.CONFIGURATION,
                UserActionKind.CHECK_CREDENTIALS,
            ),
            (
                "forbidden_403",
                _mistral_error(403, "You do not have access to this resource"),
                InferenceErrorCategory.CONFIGURATION,
                UserActionKind.CHECK_CREDENTIALS,
            ),
            (
                "rate_limit_generic_429",
                _mistral_error(429, "Rate limit exceeded. Please retry after 20s"),
                InferenceErrorCategory.TRANSIENT,
                UserActionKind.WAIT_AND_RETRY,
            ),
            (
                "bad_request_content_policy_400",
                _mistral_error(400, "Your request was rejected due to content_policy_violation"),
                InferenceErrorCategory.CONTENT,
                UserActionKind.CHANGE_INPUT,
            ),
            (
                "bad_request_generic_400",
                _mistral_error(400, "Invalid parameter: temperature must be between 0 and 1"),
                InferenceErrorCategory.CONTENT,
                UserActionKind.CHANGE_INPUT,
            ),
            (
                "server_error_500",
                _mistral_error(500, "Internal server error"),
                InferenceErrorCategory.TRANSIENT,
                UserActionKind.WAIT_AND_RETRY,
            ),
            (
                "unhandled_4xx_conflict_409",
                _mistral_error(409, "Conflict"),
                InferenceErrorCategory.CONFIGURATION,
                UserActionKind.CHANGE_INPUT,
            ),
        ],
    )
    def test_classifies_to_llm_completion_error(
        self,
        _topic: str,
        sdk_exc: BaseException,
        expected_category: InferenceErrorCategory,
        expected_action_kind: UserActionKind,
    ) -> None:
        result = _classify(sdk_exc)
        assert isinstance(result, LLMCompletionError)
        assert result.error_category is expected_category
        assert result.user_action is not None
        assert result.user_action.kind is expected_action_kind

    def test_not_found_error_yields_model_not_found_error(self) -> None:
        result = _classify(_mistral_error(404, "Model mistral-unknown not found"))
        assert isinstance(result, LLMModelNotFoundError)
        assert result.error_category is InferenceErrorCategory.CONFIGURATION
        assert result.model_handle == _MODEL_HANDLE
        assert result.user_action is not None
        assert result.user_action.kind is UserActionKind.CHANGE_MODEL
        assert _MODEL_ID in result.user_action.detail
        assert result.provider_metadata is not None
        assert result.provider_metadata.status_code == 404

    def test_transport_error_has_no_provider_metadata(self) -> None:
        """A raw transport failure carries no provider metadata — there is no HTTP response to read."""
        result = _classify(httpx.ConnectError("Connection refused"))
        assert isinstance(result, LLMCompletionError)
        assert result.provider_metadata is None

    def test_unrecognized_exception_returns_none(self) -> None:
        """A non-SDK, non-transport exception is not classified — the caller applies its own fallback."""
        assert _classify(ValueError("not an SDK error")) is None
