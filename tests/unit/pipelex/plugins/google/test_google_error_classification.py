"""Tests for ``classify_google_sdk_error``.

The classifier maps a Google GenAI SDK exception (``ServerError`` /
``ClientError``) or a raw ``httpx`` transport error to a categorized pipelex
error, or ``None`` for an unrecognized type. Verifies the error category, the
user-action kind, and the ``LLMModelNotFoundError`` specialization for a 404.
"""

from __future__ import annotations

import httpx
import pytest
from google.genai import errors as genai_errors

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError, LLMModelNotFoundError
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.plugins.google.google_error_classification import classify_google_sdk_error

_MODEL_DESC = "test-model-desc"
_MODEL_ID = "gemini-test-id"
_MODEL_HANDLE = "gemini-test"


def _client_error(code: int, message: str) -> genai_errors.ClientError:
    return genai_errors.ClientError(code, {"message": message, "status": "ERROR"}, None)


def _server_error(code: int, message: str) -> genai_errors.ServerError:
    return genai_errors.ServerError(code, {"message": message, "status": "INTERNAL"}, None)


def _classify(sdk_exc: BaseException) -> LLMCompletionError | LLMModelNotFoundError | None:
    return classify_google_sdk_error(
        sdk_exc=sdk_exc,
        model_desc=_MODEL_DESC,
        model_id=_MODEL_ID,
        model_handle=_MODEL_HANDLE,
    )


class TestClassifyGoogleSdkError:
    """``classify_google_sdk_error`` maps every recognized SDK exception to the right category."""

    @pytest.mark.parametrize(
        ("_topic", "sdk_exc", "expected_category", "expected_action_kind"),
        [
            (
                "server_error_500",
                _server_error(500, "Internal server error"),
                InferenceErrorCategory.TRANSIENT,
                UserActionKind.WAIT_AND_RETRY,
            ),
            (
                "server_error_503",
                _server_error(503, "Service unavailable"),
                InferenceErrorCategory.TRANSIENT,
                UserActionKind.WAIT_AND_RETRY,
            ),
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
                "auth_401",
                _client_error(401, "Request had invalid authentication credentials"),
                InferenceErrorCategory.CONFIGURATION,
                UserActionKind.CHECK_CREDENTIALS,
            ),
            (
                "forbidden_403",
                _client_error(403, "Permission denied on resource project"),
                InferenceErrorCategory.CONFIGURATION,
                UserActionKind.CHECK_CREDENTIALS,
            ),
            (
                "rate_limit_quota_429",
                _client_error(429, "Resource has been exhausted (e.g. check quota)"),
                InferenceErrorCategory.CAPACITY,
                UserActionKind.CHECK_BILLING,
            ),
            (
                "rate_limit_generic_429",
                _client_error(429, "Too many requests, please slow down"),
                InferenceErrorCategory.TRANSIENT,
                UserActionKind.WAIT_AND_RETRY,
            ),
            (
                "bad_request_content_policy_400",
                _client_error(400, "Your request was rejected due to content_policy_violation"),
                InferenceErrorCategory.CONTENT,
                UserActionKind.CHANGE_INPUT,
            ),
            (
                "bad_request_generic_400",
                _client_error(400, "Invalid parameter: temperature must be between 0 and 2"),
                InferenceErrorCategory.CONTENT,
                UserActionKind.CHANGE_INPUT,
            ),
            (
                "unhandled_4xx_422",
                _client_error(422, "Unprocessable entity"),
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
        result = _classify(_client_error(404, "Model gemini-99 not found"))
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
