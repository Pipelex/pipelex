"""Tests for ``classify_anthropic_sdk_error``.

The classifier maps an Anthropic SDK exception to a categorized pipelex error
(or ``None`` for an unrecognized type) without raising. Verifies the error
category, the user-action kind, and the ``AnthropicCredentialsError`` /
``LLMModelNotFoundError`` type specializations.
"""

from __future__ import annotations

import anthropic
import httpx
import pytest

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError, LLMModelNotFoundError
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.plugins.anthropic.anthropic_error_classification import classify_anthropic_sdk_error
from pipelex.plugins.anthropic.anthropic_exceptions import AnthropicCredentialsError

_MODEL_DESC = "test-model-desc"
_MODEL_ID = "claude-test-id"
_MODEL_HANDLE = "claude-test"
_REQUEST_URL = "https://api.anthropic.com/v1/messages"


def _request() -> httpx.Request:
    return httpx.Request("POST", _REQUEST_URL)


def _response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code=status_code, request=_request())


def _classify(sdk_exc: BaseException) -> LLMCompletionError | AnthropicCredentialsError | LLMModelNotFoundError | None:
    return classify_anthropic_sdk_error(
        sdk_exc=sdk_exc,
        model_desc=_MODEL_DESC,
        model_id=_MODEL_ID,
        model_handle=_MODEL_HANDLE,
    )


class TestClassifyAnthropicSdkError:
    """``classify_anthropic_sdk_error`` maps every recognized SDK exception to the right category."""

    @pytest.mark.parametrize(
        ("_topic", "sdk_exc", "expected_category", "expected_action_kind"),
        [
            (
                "rate_limit_generic",
                anthropic.RateLimitError("rate limited", response=_response(429), body=None),
                InferenceErrorCategory.TRANSIENT,
                UserActionKind.WAIT_AND_RETRY,
            ),
            (
                "rate_limit_quota",
                anthropic.RateLimitError("Your account quota has been exceeded", response=_response(429), body=None),
                InferenceErrorCategory.CAPACITY,
                UserActionKind.CHECK_BILLING,
            ),
            (
                "timeout",
                anthropic.APITimeoutError(request=_request()),
                InferenceErrorCategory.TRANSIENT,
                UserActionKind.WAIT_AND_RETRY,
            ),
            (
                "bad_request_content_policy",
                anthropic.BadRequestError("rejected due to content_policy_violation", response=_response(400), body=None),
                InferenceErrorCategory.CONTENT,
                UserActionKind.CHANGE_INPUT,
            ),
            (
                "bad_request_generic",
                anthropic.BadRequestError("invalid parameter value", response=_response(400), body=None),
                InferenceErrorCategory.CONTENT,
                UserActionKind.CHANGE_INPUT,
            ),
            (
                "connection_error",
                anthropic.APIConnectionError(message="Connection refused", request=_request()),
                InferenceErrorCategory.TRANSIENT,
                UserActionKind.WAIT_AND_RETRY,
            ),
            (
                "permission_denied_quota",
                anthropic.PermissionDeniedError("Your account quota has been exceeded", response=_response(403), body=None),
                InferenceErrorCategory.CAPACITY,
                UserActionKind.CHECK_BILLING,
            ),
            (
                "permission_denied_generic",
                anthropic.PermissionDeniedError("access to this resource is denied", response=_response(403), body=None),
                InferenceErrorCategory.CONFIGURATION,
                UserActionKind.CHECK_CREDENTIALS,
            ),
            (
                "unhandled_4xx_conflict",
                anthropic.ConflictError("conflict", response=_response(409), body=None),
                InferenceErrorCategory.CONFIGURATION,
                UserActionKind.CHANGE_INPUT,
            ),
            (
                "unhandled_5xx_server_error",
                anthropic.InternalServerError("internal error", response=_response(500), body=None),
                InferenceErrorCategory.TRANSIENT,
                UserActionKind.WAIT_AND_RETRY,
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

    def test_authentication_error_yields_credentials_error(self) -> None:
        result = _classify(anthropic.AuthenticationError("Invalid API key", response=_response(401), body=None))
        assert isinstance(result, AnthropicCredentialsError)
        assert result.error_category is InferenceErrorCategory.CONFIGURATION

    def test_not_found_error_yields_model_not_found_error(self) -> None:
        result = _classify(anthropic.NotFoundError("Model claude-99 not found", response=_response(404), body=None))
        assert isinstance(result, LLMModelNotFoundError)
        assert result.error_category is InferenceErrorCategory.CONFIGURATION
        assert result.model_handle == _MODEL_HANDLE
        assert result.user_action is not None
        assert result.user_action.kind is UserActionKind.CHANGE_MODEL
        assert _MODEL_ID in result.user_action.detail
        assert result.provider_metadata is not None
        assert result.provider_metadata.status_code == 404

    def test_unrecognized_exception_returns_none(self) -> None:
        """A non-SDK exception is not classified — the caller applies its own fallback."""
        assert _classify(ValueError("not an SDK error")) is None
