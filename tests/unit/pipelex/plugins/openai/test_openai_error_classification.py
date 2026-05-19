"""Tests for ``classify_openai_sdk_error``.

The classifier maps an OpenAI SDK exception to a categorized pipelex error
(or ``None`` for an unrecognized type) without raising. Verifies the error
category, the user-action kind, and the ``LLMModelNotFoundError`` specialization
for a ``NotFoundError``.
"""

from __future__ import annotations

import httpx
import openai
import pytest

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError, LLMModelNotFoundError
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.plugins.openai.openai_error_classification import classify_openai_sdk_error

_MODEL_DESC = "test-model-desc"
_MODEL_ID = "gpt-test-id"
_MODEL_HANDLE = "gpt-test"
_REQUEST_URL = "https://api.openai.com/v1/chat/completions"


def _request() -> httpx.Request:
    return httpx.Request("POST", _REQUEST_URL)


def _response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code=status_code, request=_request())


def _classify(sdk_exc: BaseException) -> LLMCompletionError | LLMModelNotFoundError | None:
    return classify_openai_sdk_error(
        sdk_exc=sdk_exc,
        model_desc=_MODEL_DESC,
        model_id=_MODEL_ID,
        model_handle=_MODEL_HANDLE,
    )


class TestClassifyOpenAISdkError:
    """``classify_openai_sdk_error`` maps every recognized SDK exception to the right category."""

    @pytest.mark.parametrize(
        ("_topic", "sdk_exc", "expected_category", "expected_action_kind"),
        [
            (
                "rate_limit_generic",
                openai.RateLimitError("rate limited", response=_response(429), body=None),
                InferenceErrorCategory.TRANSIENT,
                UserActionKind.WAIT_AND_RETRY,
            ),
            (
                "rate_limit_quota",
                openai.RateLimitError("You exceeded your current quota", response=_response(429), body=None),
                InferenceErrorCategory.CAPACITY,
                UserActionKind.CHECK_BILLING,
            ),
            (
                "timeout",
                openai.APITimeoutError(request=_request()),
                InferenceErrorCategory.TRANSIENT,
                UserActionKind.WAIT_AND_RETRY,
            ),
            (
                "connection_error",
                openai.APIConnectionError(message="Connection refused", request=_request()),
                InferenceErrorCategory.TRANSIENT,
                UserActionKind.WAIT_AND_RETRY,
            ),
            (
                "internal_server_error",
                openai.InternalServerError("internal error", response=_response(500), body=None),
                InferenceErrorCategory.TRANSIENT,
                UserActionKind.WAIT_AND_RETRY,
            ),
            (
                "bad_request_content_policy",
                openai.BadRequestError("rejected due to content_policy_violation", response=_response(400), body=None),
                InferenceErrorCategory.CONTENT,
                UserActionKind.CHANGE_INPUT,
            ),
            (
                "bad_request_generic",
                openai.BadRequestError("invalid parameter value", response=_response(400), body=None),
                InferenceErrorCategory.CONTENT,
                UserActionKind.CHANGE_INPUT,
            ),
            (
                "permission_denied",
                openai.PermissionDeniedError("permission denied", response=_response(403), body=None),
                InferenceErrorCategory.CONFIGURATION,
                UserActionKind.CHECK_CREDENTIALS,
            ),
            (
                "authentication_error",
                openai.AuthenticationError("Invalid API key", response=_response(401), body=None),
                InferenceErrorCategory.CONFIGURATION,
                UserActionKind.CHECK_CREDENTIALS,
            ),
            (
                "unhandled_4xx_conflict",
                openai.ConflictError("conflict", response=_response(409), body=None),
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
        result = _classify(openai.NotFoundError("Model gpt-99 not found", response=_response(404), body=None))
        assert isinstance(result, LLMModelNotFoundError)
        assert result.error_category is InferenceErrorCategory.CONFIGURATION
        assert result.model_handle == _MODEL_HANDLE
        assert result.user_action is not None
        assert result.user_action.kind is UserActionKind.CHANGE_MODEL
        assert _MODEL_ID in result.user_action.detail
        assert result.provider_metadata is not None
        assert result.provider_metadata.status_code == 404

    def test_not_found_with_propagation_race_phrase_still_yields_model_not_found(self) -> None:
        """The shared classifier stays gateway-agnostic: a 404 carrying the gateway deployment-
        propagation-race phrase is still LLMModelNotFoundError. Only the gateway LLM workers demote
        it (see tests/unit/pipelex/plugins/gateway/test_gateway_llm_worker_error_handling.py).
        """
        result = _classify(openai.NotFoundError("The specified deployment could not be found", response=_response(404), body=None))
        assert isinstance(result, LLMModelNotFoundError)
        assert result.error_category is InferenceErrorCategory.CONFIGURATION

    def test_unrecognized_exception_returns_none(self) -> None:
        """A non-SDK exception is not classified — the caller applies its own fallback."""
        assert _classify(ValueError("not an SDK error")) is None
