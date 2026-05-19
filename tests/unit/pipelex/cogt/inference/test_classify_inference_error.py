"""Tests for ``classify_inference_error`` — the provider-blind Classify step.

These tests are provider-blind: they build synthetic ``ProviderErrorMetadata``
envelopes and assert the classification, with no SDK installed or imported.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserActionKind
from pipelex.cogt.inference.error_classify import classify_inference_error
from pipelex.cogt.inference.provider_name import ProviderName


class _TestCases:
    # (topic, provider, sdk_exception_type, message, status_code,
    #  expected_category, expected_action, expected_is_model_not_found)
    PARITY: ClassVar[list[tuple[str, ProviderName, str, str, int | None, InferenceErrorCategory, UserActionKind, bool]]] = [
        (
            "rate_limit_429",
            ProviderName.OPENAI,
            "RateLimitError",
            "Rate limit reached",
            429,
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
            False,
        ),
        (
            "quota_429",
            ProviderName.OPENAI,
            "RateLimitError",
            "You exceeded your current quota",
            429,
            InferenceErrorCategory.CAPACITY,
            UserActionKind.CHECK_BILLING,
            False,
        ),
        (
            "payment_required_402",
            ProviderName.MISTRAL,
            "SDKError",
            "Payment required",
            402,
            InferenceErrorCategory.CAPACITY,
            UserActionKind.CHECK_BILLING,
            False,
        ),
        (
            "auth_401",
            ProviderName.OPENAI,
            "AuthenticationError",
            "Invalid API key",
            401,
            InferenceErrorCategory.CONFIGURATION,
            UserActionKind.CHECK_CREDENTIALS,
            False,
        ),
        (
            "permission_denied_403",
            ProviderName.OPENAI,
            "PermissionDeniedError",
            "Forbidden",
            403,
            InferenceErrorCategory.CONFIGURATION,
            UserActionKind.CHECK_CREDENTIALS,
            False,
        ),
        (
            "permission_denied_403_quota_anthropic",
            ProviderName.ANTHROPIC,
            "PermissionDeniedError",
            "Your credit balance is too low",
            403,
            InferenceErrorCategory.CAPACITY,
            UserActionKind.CHECK_BILLING,
            False,
        ),
        (
            "not_found_404",
            ProviderName.OPENAI,
            "NotFoundError",
            "The model does not exist",
            404,
            InferenceErrorCategory.CONFIGURATION,
            UserActionKind.CHANGE_MODEL,
            True,
        ),
        (
            "bad_request_400",
            ProviderName.OPENAI,
            "BadRequestError",
            "Bad request",
            400,
            InferenceErrorCategory.CONTENT,
            UserActionKind.CHANGE_INPUT,
            False,
        ),
        (
            "unprocessable_422_is_unrecognized_4xx",
            ProviderName.OPENAI,
            "UnprocessableEntityError",
            "Unprocessable entity",
            422,
            InferenceErrorCategory.CONFIGURATION,
            UserActionKind.CHANGE_INPUT,
            False,
        ),
        (
            "internal_server_error_500",
            ProviderName.OPENAI,
            "InternalServerError",
            "Internal server error",
            500,
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
            False,
        ),
        (
            "service_unavailable_503",
            ProviderName.GOOGLE,
            "ServerError",
            "Service unavailable",
            503,
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
            False,
        ),
        (
            "conflict_409_other_4xx",
            ProviderName.OPENAI,
            "ConflictError",
            "Conflict",
            409,
            InferenceErrorCategory.CONFIGURATION,
            UserActionKind.CHANGE_INPUT,
            False,
        ),
        (
            "statusless_connection_error",
            ProviderName.OPENAI,
            "APIConnectionError",
            "Connection failed",
            None,
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
            False,
        ),
        (
            "statusless_timeout",
            ProviderName.OPENAI,
            "APITimeoutError",
            "Request timed out",
            None,
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
            False,
        ),
        (
            "statusless_validation_error",
            ProviderName.OPENAI,
            "ValidationError",
            "Schema validation failed",
            None,
            InferenceErrorCategory.CONTENT,
            UserActionKind.CHANGE_INPUT,
            False,
        ),
        (
            "statusless_file_not_found",
            ProviderName.DOCLING,
            "FileNotFoundError",
            "No such file",
            None,
            InferenceErrorCategory.CONTENT,
            UserActionKind.CHANGE_INPUT,
            False,
        ),
        (
            "statusless_os_error",
            ProviderName.DOCLING,
            "OSError",
            "I/O error",
            None,
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
            False,
        ),
        (
            "statusless_linkup_auth",
            ProviderName.LINKUP,
            "LinkupAuthenticationError",
            "Authentication failed",
            None,
            InferenceErrorCategory.CONFIGURATION,
            UserActionKind.CHECK_CREDENTIALS,
            False,
        ),
        (
            "statusless_linkup_credit",
            ProviderName.LINKUP,
            "LinkupInsufficientCreditError",
            "Insufficient credits",
            None,
            InferenceErrorCategory.CAPACITY,
            UserActionKind.CHECK_BILLING,
            False,
        ),
        (
            "statusless_fal_missing_credentials",
            ProviderName.FAL,
            "MissingCredentialsError",
            "FAL API key is not configured",
            None,
            InferenceErrorCategory.CONFIGURATION,
            UserActionKind.CHECK_CREDENTIALS,
            False,
        ),
        (
            "statusless_fal_client_error",
            ProviderName.FAL,
            "FalClientError",
            "FAL SDK failed without a recoverable HTTP status",
            None,
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
            False,
        ),
        (
            "statusless_unrecognized_unknown",
            ProviderName.OPENAI,
            "BrandNewSdkError",
            "Something nobody has seen before",
            None,
            InferenceErrorCategory.UNKNOWN,
            UserActionKind.CONTACT_SUPPORT,
            False,
        ),
    ]


class TestClassifyInferenceError:
    @pytest.mark.parametrize(
        (
            "_topic",
            "provider",
            "sdk_exception_type",
            "message",
            "status_code",
            "expected_category",
            "expected_action",
            "expected_model_not_found",
        ),
        _TestCases.PARITY,
    )
    def test_classify_parity_matrix(
        self,
        _topic: str,
        provider: ProviderName,
        sdk_exception_type: str,
        message: str,
        status_code: int | None,
        expected_category: InferenceErrorCategory,
        expected_action: UserActionKind,
        expected_model_not_found: bool,
    ) -> None:
        metadata = ProviderErrorMetadata(
            provider=provider,
            sdk_exception_type=sdk_exception_type,
            message=message,
            status_code=status_code,
        )

        result = classify_inference_error(metadata)

        assert result.category == expected_category
        assert result.user_action_kind == expected_action
        assert result.is_model_not_found is expected_model_not_found

    @pytest.mark.parametrize(
        "provider",
        [
            ProviderName.OPENAI,
            ProviderName.ANTHROPIC,
            ProviderName.GOOGLE,
            ProviderName.MISTRAL,
            ProviderName.BEDROCK,
            ProviderName.GATEWAY,
            ProviderName.AZURE,
            ProviderName.FAL,
            ProviderName.HUGGINGFACE,
        ],
    )
    def test_plain_429_is_transient_for_every_provider(self, provider: ProviderName) -> None:
        """A 429 with no quota signal classifies as TRANSIENT for every provider."""
        metadata = ProviderErrorMetadata(
            provider=provider,
            sdk_exception_type="RateLimitError",
            message="Too many requests",
            status_code=429,
        )

        result = classify_inference_error(metadata)

        assert result.category == InferenceErrorCategory.TRANSIENT
        assert result.user_action_kind == UserActionKind.WAIT_AND_RETRY
