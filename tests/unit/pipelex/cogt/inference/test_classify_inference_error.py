"""Tests for ``classify_inference_error`` — the provider-blind Classify step.

These tests are provider-blind: they build synthetic ``ProviderErrorMetadata``
envelopes and assert the classification, with no SDK installed or imported.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pytest
from mthds.protocol.problem.registry import CoreCode
from pydantic import ValidationError

from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserActionKind
from pipelex.cogt.inference.error_classify import ClassificationResult, InferenceErrorFamily, classify_inference_error
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode

if TYPE_CHECKING:
    from pipelex.errors.error_codes import ErrorCode

_LLM = InferenceErrorFamily.LLM
_IMG_GEN = InferenceErrorFamily.IMG_GEN
_EXTRACT = InferenceErrorFamily.EXTRACT
_SEARCH = InferenceErrorFamily.SEARCH


class _TestCases:
    # (topic, provider, sdk_exception_type, message, status_code, family,
    #  expected_category, expected_action, expected_error_code, expected_is_model_not_found)
    PARITY: ClassVar[
        list[tuple[str, ProviderName, str, str, int | None, InferenceErrorFamily, InferenceErrorCategory, UserActionKind, ErrorCode, bool]]
    ] = [
        (
            "rate_limit_429",
            ProviderName.OPENAI,
            "RateLimitError",
            "Rate limit reached",
            429,
            _LLM,
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
            CoreCode.PROVIDER_RATE_LIMITED,
            False,
        ),
        (
            "rate_limit_429_on_an_image_generation_ran_nothing",
            ProviderName.OPENAI,
            "RateLimitError",
            "Rate limit reached",
            429,
            _IMG_GEN,
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
            CoreCode.PROVIDER_RATE_LIMITED,
            False,
        ),
        (
            "quota_429",
            ProviderName.OPENAI,
            "RateLimitError",
            "You exceeded your current quota",
            429,
            _LLM,
            InferenceErrorCategory.CAPACITY,
            UserActionKind.CHECK_BILLING,
            CoreCode.PROVIDER_QUOTA_EXHAUSTED,
            False,
        ),
        (
            "payment_required_402",
            ProviderName.MISTRAL,
            "SDKError",
            "Payment required",
            402,
            _LLM,
            InferenceErrorCategory.CAPACITY,
            UserActionKind.CHECK_BILLING,
            CoreCode.PROVIDER_QUOTA_EXHAUSTED,
            False,
        ),
        (
            "auth_401",
            ProviderName.OPENAI,
            "AuthenticationError",
            "Invalid API key",
            401,
            _LLM,
            InferenceErrorCategory.CONFIGURATION,
            UserActionKind.CHECK_CREDENTIALS,
            CoreCode.PROVIDER_CREDENTIAL_REFUSED,
            False,
        ),
        (
            "permission_denied_403",
            ProviderName.OPENAI,
            "PermissionDeniedError",
            "Forbidden",
            403,
            _LLM,
            InferenceErrorCategory.CONFIGURATION,
            UserActionKind.CHECK_CREDENTIALS,
            CoreCode.PROVIDER_CREDENTIAL_REFUSED,
            False,
        ),
        (
            "permission_denied_403_quota_anthropic",
            ProviderName.ANTHROPIC,
            "PermissionDeniedError",
            "Your credit balance is too low",
            403,
            _LLM,
            InferenceErrorCategory.CAPACITY,
            UserActionKind.CHECK_BILLING,
            CoreCode.PROVIDER_QUOTA_EXHAUSTED,
            False,
        ),
        (
            "not_found_404",
            ProviderName.OPENAI,
            "NotFoundError",
            "The model does not exist",
            404,
            _LLM,
            InferenceErrorCategory.CONFIGURATION,
            UserActionKind.CHANGE_MODEL,
            CoreCode.MODEL_UNAVAILABLE,
            True,
        ),
        (
            "bad_request_400_is_a_request_of_ours",
            ProviderName.OPENAI,
            "BadRequestError",
            "Bad request",
            400,
            _LLM,
            InferenceErrorCategory.CONTENT,
            UserActionKind.CHANGE_INPUT,
            CoreCode.RUNTIME_UNEXPECTED,
            False,
        ),
        (
            "bad_request_400_with_a_content_policy_signal",
            ProviderName.OPENAI,
            "BadRequestError",
            "Your request was rejected as a result of our safety system",
            400,
            _IMG_GEN,
            InferenceErrorCategory.CONTENT,
            UserActionKind.CHANGE_INPUT,
            CoreCode.MODEL_CONTENT_REFUSED,
            False,
        ),
        (
            "request_too_large_413",
            ProviderName.ANTHROPIC,
            "RequestTooLargeError",
            "Request too large",
            413,
            _LLM,
            InferenceErrorCategory.CONFIGURATION,
            UserActionKind.CHANGE_INPUT,
            CoreCode.INPUT_TOO_LARGE,
            False,
        ),
        (
            "request_timeout_408",
            ProviderName.OPENAI,
            "APIStatusError",
            "Request timeout",
            408,
            _LLM,
            InferenceErrorCategory.CONFIGURATION,
            UserActionKind.CHANGE_INPUT,
            CoreCode.PROVIDER_TIMEOUT,
            False,
        ),
        (
            "unprocessable_422_is_unrecognized_4xx",
            ProviderName.OPENAI,
            "UnprocessableEntityError",
            "Unprocessable entity",
            422,
            _LLM,
            InferenceErrorCategory.CONFIGURATION,
            UserActionKind.CHANGE_INPUT,
            CoreCode.RUNTIME_UNEXPECTED,
            False,
        ),
        (
            "internal_server_error_500",
            ProviderName.OPENAI,
            "InternalServerError",
            "Internal server error",
            500,
            _LLM,
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
            CoreCode.PROVIDER_FAILED,
            False,
        ),
        (
            "bad_gateway_502",
            ProviderName.OPENAI,
            "InternalServerError",
            "Bad gateway",
            502,
            _LLM,
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
            CoreCode.PROVIDER_FAILED,
            False,
        ),
        (
            "service_unavailable_503",
            ProviderName.GOOGLE,
            "ServerError",
            "Service unavailable",
            503,
            _LLM,
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
            CoreCode.PROVIDER_UNAVAILABLE,
            False,
        ),
        (
            "gateway_timeout_504",
            ProviderName.GOOGLE,
            "ServerError",
            "Gateway timeout",
            504,
            _EXTRACT,
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
            CoreCode.PROVIDER_TIMEOUT,
            False,
        ),
        (
            "anthropic_overloaded_529",
            ProviderName.ANTHROPIC,
            "OverloadedError",
            "Overloaded",
            529,
            _LLM,
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
            CoreCode.PROVIDER_UNAVAILABLE,
            False,
        ),
        (
            "server_error_on_an_image_generation_may_have_run",
            ProviderName.OPENAI,
            "InternalServerError",
            "Internal server error",
            500,
            _IMG_GEN,
            InferenceErrorCategory.AMBIGUOUS,
            UserActionKind.WAIT_AND_RETRY,
            CoreCode.PROVIDER_OUTCOME_UNKNOWN,
            False,
        ),
        (
            "conflict_409_other_4xx",
            ProviderName.OPENAI,
            "ConflictError",
            "Conflict",
            409,
            _LLM,
            InferenceErrorCategory.CONFIGURATION,
            UserActionKind.CHANGE_INPUT,
            CoreCode.RUNTIME_UNEXPECTED,
            False,
        ),
        (
            "non_error_status_on_an_error_envelope",
            ProviderName.AZURE,
            "JSONDecodeError",
            "Expecting value",
            200,
            _IMG_GEN,
            InferenceErrorCategory.UNKNOWN,
            UserActionKind.CONTACT_SUPPORT,
            CoreCode.PROVIDER_RESPONSE_INVALID,
            False,
        ),
        (
            "statusless_connection_error",
            ProviderName.OPENAI,
            "APIConnectionError",
            "Connection failed",
            None,
            _LLM,
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
            CoreCode.PROVIDER_UNAVAILABLE,
            False,
        ),
        (
            "statusless_sdk_connection_error_on_an_image_generation_may_have_been_sent",
            ProviderName.OPENAI,
            "APIConnectionError",
            "Connection failed",
            None,
            _IMG_GEN,
            InferenceErrorCategory.AMBIGUOUS,
            UserActionKind.WAIT_AND_RETRY,
            CoreCode.PROVIDER_OUTCOME_UNKNOWN,
            False,
        ),
        (
            "statusless_httpx_connect_error_on_an_image_generation_was_never_sent",
            ProviderName.AZURE,
            "ConnectError",
            "Connection refused",
            None,
            _IMG_GEN,
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
            CoreCode.PROVIDER_UNAVAILABLE,
            False,
        ),
        (
            "statusless_connect_timeout_is_an_outage_not_a_timeout",
            ProviderName.AZURE,
            "ConnectTimeout",
            "Connect timed out",
            None,
            _LLM,
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
            CoreCode.PROVIDER_UNAVAILABLE,
            False,
        ),
        (
            "statusless_timeout",
            ProviderName.OPENAI,
            "APITimeoutError",
            "Request timed out",
            None,
            _LLM,
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
            CoreCode.PROVIDER_TIMEOUT,
            False,
        ),
        (
            "statusless_read_timeout_on_an_image_generation",
            ProviderName.HUGGINGFACE,
            "InferenceTimeoutError",
            "Inference timed out",
            None,
            _IMG_GEN,
            InferenceErrorCategory.AMBIGUOUS,
            UserActionKind.WAIT_AND_RETRY,
            CoreCode.PROVIDER_OUTCOME_UNKNOWN,
            False,
        ),
        (
            "statusless_validation_error",
            ProviderName.OPENAI,
            "ValidationError",
            "Schema validation failed",
            None,
            _LLM,
            InferenceErrorCategory.CONTENT,
            UserActionKind.CHANGE_INPUT,
            CoreCode.MODEL_OUTPUT_SCHEMA_MISMATCH,
            False,
        ),
        (
            "statusless_file_not_found",
            ProviderName.DOCLING,
            "FileNotFoundError",
            "No such file",
            None,
            _EXTRACT,
            InferenceErrorCategory.CONTENT,
            UserActionKind.CHANGE_INPUT,
            CoreCode.INPUT_REFERENCE_NOT_FOUND,
            False,
        ),
        (
            "statusless_file_that_does_not_parse",
            ProviderName.PYPDFIUM2,
            "ValueError",
            "Failed to load document",
            None,
            _EXTRACT,
            InferenceErrorCategory.CONTENT,
            UserActionKind.CHANGE_INPUT,
            CoreCode.INPUT_FILE_UNREADABLE,
            False,
        ),
        (
            "statusless_os_error",
            ProviderName.DOCLING,
            "OSError",
            "I/O error",
            None,
            _EXTRACT,
            InferenceErrorCategory.UNKNOWN,
            UserActionKind.CONTACT_SUPPORT,
            CoreCode.RUNTIME_UNEXPECTED,
            False,
        ),
        (
            "statusless_linkup_auth",
            ProviderName.LINKUP,
            "LinkupAuthenticationError",
            "Authentication failed",
            None,
            _SEARCH,
            InferenceErrorCategory.CONFIGURATION,
            UserActionKind.CHECK_CREDENTIALS,
            CoreCode.PROVIDER_CREDENTIAL_REFUSED,
            False,
        ),
        (
            "statusless_linkup_credit",
            ProviderName.LINKUP,
            "LinkupInsufficientCreditError",
            "Insufficient credits",
            None,
            _SEARCH,
            InferenceErrorCategory.CAPACITY,
            UserActionKind.CHECK_BILLING,
            CoreCode.PROVIDER_QUOTA_EXHAUSTED,
            False,
        ),
        (
            "statusless_linkup_failed_fetch_is_the_caller_s_url",
            ProviderName.LINKUP,
            "LinkupFailedFetchError",
            "Failed to fetch the page",
            None,
            _EXTRACT,
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
            CoreCode.INPUT_URL_UNREACHABLE,
            False,
        ),
        (
            "statusless_linkup_no_result",
            ProviderName.LINKUP,
            "LinkupNoResultError",
            "No result",
            None,
            _SEARCH,
            InferenceErrorCategory.CONTENT,
            UserActionKind.CHANGE_INPUT,
            CoreCode.MODEL_NO_RESULT,
            False,
        ),
        (
            "statusless_fal_missing_credentials",
            ProviderName.FAL,
            "MissingCredentialsError",
            "FAL API key is not configured",
            None,
            _IMG_GEN,
            InferenceErrorCategory.CONFIGURATION,
            UserActionKind.CHECK_CREDENTIALS,
            PipelexErrorCode.CONFIG_CREDENTIAL_MISSING,
            False,
        ),
        (
            "statusless_fal_client_error_may_have_run",
            ProviderName.FAL,
            "FalClientError",
            "FAL SDK failed without a recoverable HTTP status",
            None,
            _IMG_GEN,
            InferenceErrorCategory.AMBIGUOUS,
            UserActionKind.WAIT_AND_RETRY,
            CoreCode.PROVIDER_OUTCOME_UNKNOWN,
            False,
        ),
        (
            "statusless_unrecognized_unknown",
            ProviderName.OPENAI,
            "BrandNewSdkError",
            "Something nobody has seen before",
            None,
            _LLM,
            InferenceErrorCategory.UNKNOWN,
            UserActionKind.CONTACT_SUPPORT,
            CoreCode.RUNTIME_UNEXPECTED,
            False,
        ),
        # httpx TransportError subclasses whose class names lack a recognized network token
        # (e.g. ReadError, WriteError, CloseError, RemoteProtocolError, ProxyError) must still
        # classify as TRANSIENT — otherwise genuine transport failures slip through to UNKNOWN
        # and retry policy is suppressed.
        (
            "statusless_httpx_read_error",
            ProviderName.AZURE,
            "ReadError",
            "stream read failed",
            None,
            _LLM,
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
            CoreCode.PROVIDER_UNAVAILABLE,
            False,
        ),
        (
            "statusless_httpx_remote_protocol_error",
            ProviderName.AZURE,
            "RemoteProtocolError",
            "server disconnected",
            None,
            _LLM,
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
            CoreCode.PROVIDER_UNAVAILABLE,
            False,
        ),
        (
            "statusless_httpx_proxy_error",
            ProviderName.AZURE,
            "ProxyError",
            "proxy refused",
            None,
            _LLM,
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
            CoreCode.PROVIDER_UNAVAILABLE,
            False,
        ),
    ]


class TestClassifyInferenceError:
    @pytest.mark.parametrize(
        ("_topic", "provider", "sdk_exception_type", "message", "status_code", "provider_error_code", "expected_category", "expected_error_code"),
        [
            (
                "fal_content_policy_on_422",
                ProviderName.FAL,
                "FalClientHTTPError",
                "Image rejected",
                422,
                "ContentPolicyViolation",
                InferenceErrorCategory.CONTENT,
                CoreCode.MODEL_CONTENT_REFUSED,
            ),
            (
                "content_policy_message_on_422",
                ProviderName.OPENAI,
                "UnprocessableEntityError",
                "content_filter triggered for prompt",
                422,
                None,
                InferenceErrorCategory.CONTENT,
                CoreCode.MODEL_CONTENT_REFUSED,
            ),
            (
                "plain_422_stays_configuration",
                ProviderName.OPENAI,
                "UnprocessableEntityError",
                "Unprocessable entity",
                422,
                None,
                InferenceErrorCategory.CONFIGURATION,
                CoreCode.RUNTIME_UNEXPECTED,
            ),
            (
                "bedrock_service_quota_via_error_code",
                ProviderName.BEDROCK,
                "ClientError",
                "An error occurred",
                400,
                "ServiceQuotaExceededException",
                InferenceErrorCategory.CAPACITY,
                CoreCode.PROVIDER_QUOTA_EXHAUSTED,
            ),
        ],
    )
    def test_classify_extra_signals(
        self,
        _topic: str,
        provider: ProviderName,
        sdk_exception_type: str,
        message: str,
        status_code: int | None,
        provider_error_code: str | None,
        expected_category: InferenceErrorCategory,
        expected_error_code: ErrorCode,
    ) -> None:
        """Extra signals beyond status code: provider_error_code and content-policy detection."""
        metadata = ProviderErrorMetadata(
            provider=provider,
            sdk_exception_type=sdk_exception_type,
            message=message,
            status_code=status_code,
            provider_error_code=provider_error_code,
        )

        result = classify_inference_error(metadata, family=InferenceErrorFamily.IMG_GEN)

        assert result.category == expected_category
        assert result.error_code == expected_error_code

    @pytest.mark.parametrize(
        (
            "_topic",
            "provider",
            "sdk_exception_type",
            "message",
            "status_code",
            "family",
            "expected_category",
            "expected_action",
            "expected_error_code",
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
        family: InferenceErrorFamily,
        expected_category: InferenceErrorCategory,
        expected_action: UserActionKind,
        expected_error_code: ErrorCode,
        expected_model_not_found: bool,
    ) -> None:
        metadata = ProviderErrorMetadata(
            provider=provider,
            sdk_exception_type=sdk_exception_type,
            message=message,
            status_code=status_code,
        )

        result = classify_inference_error(metadata, family=family)

        assert result.category == expected_category
        assert result.user_action_kind == expected_action
        assert result.error_code == expected_error_code
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

        result = classify_inference_error(metadata, family=InferenceErrorFamily.LLM)

        assert result.category == InferenceErrorCategory.TRANSIENT
        assert result.user_action_kind == UserActionKind.WAIT_AND_RETRY
        assert result.error_code == CoreCode.PROVIDER_RATE_LIMITED

    @pytest.mark.parametrize(
        ("category", "error_code", "is_model_not_found", "expected_fragment"),
        [
            (InferenceErrorCategory.UNKNOWN, CoreCode.PIPE_PROMPT_EMPTY, False, "not one an inference failure class declares"),
            (InferenceErrorCategory.UNKNOWN, PipelexErrorCode.CONFIG_VARIABLE_MISSING, False, "not one an inference failure class declares"),
            (InferenceErrorCategory.UNKNOWN, CoreCode.PROVIDER_FAILED, True, "reports 'model.unavailable'"),
            # The run repeats a transient call, so its report cannot say no retry clears it.
            (InferenceErrorCategory.TRANSIENT, CoreCode.RUNTIME_UNEXPECTED, False, "reports a code that invites a retry"),
        ],
    )
    def test_a_classification_refuses_a_code_its_render_could_not_report(
        self,
        category: InferenceErrorCategory,
        error_code: ErrorCode,
        is_model_not_found: bool,
        expected_fragment: str,
    ) -> None:
        """The render constructs a family's class with the code, so a code no family class declares, or its category contradicts, is refused first."""
        with pytest.raises(ValidationError, match=expected_fragment):
            ClassificationResult(
                category=category,
                user_action_kind=UserActionKind.CONTACT_SUPPORT,
                error_code=error_code,
                is_model_not_found=is_model_not_found,
            )
