"""Tests for the ``ProviderErrorMetadata`` Pydantic model.

This model carries structured SDK metadata alongside every inference error so
downstream consumers (retry / temporal / CLI) do not have to scrape it back
from the exception chain.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from mthds.protocol.problem.registry import CoreCode
from pydantic import ValidationError

from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, extract_azure_metadata
from pipelex.cogt.inference.error_classify import InferenceErrorFamily, classify_inference_error
from pipelex.cogt.inference.provider_name import ProviderName


class TestProviderErrorMetadata:
    """``ProviderErrorMetadata`` is a Pydantic model with two required fields and the rest optional."""

    def test_accepts_full_payload(self) -> None:
        metadata = ProviderErrorMetadata(
            provider=ProviderName.ANTHROPIC,
            sdk_exception_type="RateLimitError",
            status_code=429,
            request_id="req_abc123",
            retry_after_seconds=5.0,
            provider_error_code="rate_limit_error",
            body={"error": {"type": "rate_limit_error"}},
        )

        assert metadata.provider == ProviderName.ANTHROPIC
        assert metadata.sdk_exception_type == "RateLimitError"
        assert metadata.status_code == 429
        assert metadata.request_id == "req_abc123"
        assert metadata.retry_after_seconds == 5.0
        assert metadata.provider_error_code == "rate_limit_error"
        assert metadata.body == {"error": {"type": "rate_limit_error"}}

    def test_optional_fields_default_to_none(self) -> None:
        metadata = ProviderErrorMetadata(provider=ProviderName.ANTHROPIC, sdk_exception_type="APIConnectionError")

        assert metadata.status_code is None
        assert metadata.request_id is None
        assert metadata.retry_after_seconds is None
        assert metadata.provider_error_code is None
        assert metadata.body is None

    def test_provider_is_required(self) -> None:
        with pytest.raises(ValidationError):
            ProviderErrorMetadata(sdk_exception_type="RateLimitError")  # type: ignore[call-arg]

    def test_sdk_exception_type_is_required(self) -> None:
        with pytest.raises(ValidationError):
            ProviderErrorMetadata(provider=ProviderName.ANTHROPIC)  # type: ignore[call-arg]

    def test_round_trips_via_model_dump_and_validate(self) -> None:
        metadata = ProviderErrorMetadata(
            provider=ProviderName.ANTHROPIC,
            sdk_exception_type="RateLimitError",
            status_code=429,
            retry_after_seconds=5.0,
        )

        dumped = metadata.model_dump()
        rebuilt = ProviderErrorMetadata.model_validate(dumped)

        assert rebuilt == metadata

    def test_body_is_excluded_from_serialization(self) -> None:
        """``body`` may carry account ids or credential fragments, so it is dropped
        from serialization while staying readable in-process.
        """
        metadata = ProviderErrorMetadata(
            provider=ProviderName.ANTHROPIC,
            sdk_exception_type="RateLimitError",
            status_code=429,
            body={"error": {"type": "rate_limit_error", "account_id": "acct_secret"}},
        )

        assert metadata.body == {"error": {"type": "rate_limit_error", "account_id": "acct_secret"}}
        assert "body" not in metadata.model_dump()
        assert "acct_secret" not in metadata.model_dump_json()

    def test_message_defaults_to_empty_string(self) -> None:
        metadata = ProviderErrorMetadata(provider=ProviderName.OPENAI, sdk_exception_type="APIConnectionError")

        assert metadata.message == ""

    @pytest.mark.parametrize(
        ("_topic", "provider", "message", "status_code", "provider_error_code", "expected"),
        [
            ("openai_quota_code_429", ProviderName.OPENAI, "You exceeded your current quota", 429, "insufficient_quota", True),
            # The words decide nothing: a 429 with no quota code is a rate limit
            ("openai_quota_wording_429_no_code", ProviderName.OPENAI, "You exceeded your current quota", 429, None, False),
            ("openai_rate_limit", ProviderName.OPENAI, "Rate limit reached", 429, None, False),
            ("anthropic_billing_error_402", ProviderName.ANTHROPIC, "Error code: 402", 402, "billing_error", True),
            # Anthropic's spend sentences are read from the body's message alone, which this metadata does not carry
            ("anthropic_credit_wording_no_body", ProviderName.ANTHROPIC, "Your credit balance is too low", 400, "invalid_request_error", False),
            ("google_402_is_quota", ProviderName.GOOGLE, "payment required", 402, None, True),
            ("google_429_quota_wording", ProviderName.GOOGLE, "Resource has been exhausted (e.g. check quota)", 429, "RESOURCE_EXHAUSTED", False),
            ("mistral_402_is_quota", ProviderName.MISTRAL, "payment required", 402, None, True),
            ("mistral_429_quota_wording", ProviderName.MISTRAL, "quota exceeded", 429, None, False),
            ("mistral_429_plain_rate_limit", ProviderName.MISTRAL, "too many requests", 429, None, False),
            ("gateway_402_is_quota", ProviderName.GATEWAY, "payment required", 402, None, True),
            ("azure_never_quota", ProviderName.AZURE, "quota exceeded", 429, None, False),
            # AWS documents it as resubmittable later: a throttle on its 400, not a spent quota
            (
                "bedrock_service_quota_exceeded_is_a_throttle",
                ProviderName.BEDROCK,
                "An error occurred",
                400,
                "ServiceQuotaExceededException",
                False,
            ),
            (
                "bedrock_quota_wording_no_code",
                ProviderName.BEDROCK,
                "Service quota exceeded for this model",
                400,
                None,
                False,
            ),
            (
                "bedrock_plain_validation_not_quota",
                ProviderName.BEDROCK,
                "Validation failed for input",
                400,
                "ValidationException",
                False,
            ),
        ],
    )
    def test_is_quota_exhaustion_dispatches_on_provider(
        self,
        _topic: str,
        provider: ProviderName,
        message: str,
        status_code: int | None,
        provider_error_code: str | None,
        expected: bool,
    ) -> None:
        metadata = ProviderErrorMetadata(
            provider=provider,
            sdk_exception_type="RateLimitError",
            message=message,
            status_code=status_code,
            provider_error_code=provider_error_code,
        )

        assert metadata.is_quota_exhaustion is expected

    @pytest.mark.parametrize(
        ("_topic", "message", "provider_error_code", "expected"),
        [
            ("safety_system", "Request blocked by safety system", None, True),
            ("content_filter", "content_filter triggered", None, True),
            ("plain_message", "Something else went wrong", None, False),
            ("fal_content_policy_violation_code", "Request rejected by provider", "ContentPolicyViolation", True),
            ("non_content_provider_error_code", "Some error", "ValidationError", False),
        ],
    )
    def test_is_content_policy_violation(self, _topic: str, message: str, provider_error_code: str | None, expected: bool) -> None:
        metadata = ProviderErrorMetadata(
            provider=ProviderName.OPENAI,
            sdk_exception_type="BadRequestError",
            message=message,
            provider_error_code=provider_error_code,
        )

        assert metadata.is_content_policy_violation is expected

    @pytest.mark.parametrize(
        ("_topic", "message", "provider_error_code", "body", "expected"),
        [
            ("openai_code_in_the_body", "Error code: 400", "invalid_request_error", {"code": "context_length_exceeded"}, True),
            ("gateway_code_first", "Request failed", "context_length_exceeded", None, True),
            ("openai_earlier_wording", "This model's maximum context length is 8192 tokens", None, None, True),
            ("openai_current_wording", "Your input exceeds the context window of this model", None, None, True),
            ("anthropic", "prompt is too long: 208310 tokens > 200000 maximum", None, None, True),
            ("anthropic_with_max_tokens", "input length and `max_tokens` exceed context limit: 197202 + 8192 > 200000", None, None, True),
            ("bedrock", "Input is too long for requested model.", None, None, True),
            ("bedrock_nova", "Input Tokens Exceeded: Number of input tokens exceeds maximum length.", "ValidationException", None, True),
            ("bedrock_titan", "Too many input tokens. Max input tokens: 8192, request input token count: 9000", "ValidationException", None, True),
            ("bedrock_openai_engine", "prompt tokens (300000) exceed model maximum (262144)", "ValidationException", None, True),
            # The same words about a parameter over its bound, which is the request's fault, not the input's length
            ("a_parameter_over_the_model_maximum", "max_tokens (200000) exceed model maximum (8192)", "ValidationException", None, False),
            # Bedrock's throttle, whose "too many tokens" names no window
            ("bedrock_throttle_wording", "Too many tokens per day, please wait before trying again.", "ThrottlingException", None, False),
            ("gemini", "The input token count (1234567) exceeds the maximum number of tokens allowed (1048576).", None, None, True),
            (
                "a_parameter_refused",
                "Invalid value for 'temperature': must be between 0 and 2",
                "invalid_request_error",
                {"code": "invalid_value"},
                False,
            ),
            ("a_missing_field", "max_tokens: Field required", None, None, False),
            ("a_field_too_long", "tools.0.description: tool description input is too long", None, None, False),
            ("a_size_limit", "Request exceeds the maximum size", "request_too_large", None, False),
        ],
    )
    def test_is_context_window_exceeded(self, _topic: str, message: str, provider_error_code: str | None, body: Any, expected: bool) -> None:
        metadata = ProviderErrorMetadata(
            provider=ProviderName.OPENAI,
            sdk_exception_type="BadRequestError",
            message=message,
            status_code=400,
            provider_error_code=provider_error_code,
            body=body,
        )

        assert metadata.is_context_window_exceeded is expected

    def test_is_context_window_exceeded_reads_the_wording_in_the_body(self) -> None:
        """A raw httpx error renders only its status and URL, so the provider's wording is in the body alone."""
        body = {
            "error": {
                "code": "invalid_request",
                "message": "This model's maximum context length is 4096 tokens. However, your prompt resulted in 5210 tokens.",
            }
        }
        request = httpx.Request("POST", "https://test.openai.azure.com/openai/deployments/flux/images/generations")
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            httpx.Response(status_code=400, json=body, request=request).raise_for_status()
        metadata = extract_azure_metadata(exc_info.value)
        assert "context" not in metadata.message.lower()

        assert metadata.is_context_window_exceeded is True
        classification = classify_inference_error(metadata, family=InferenceErrorFamily.IMG_GEN)
        assert classification.error_code == CoreCode.MODEL_CONTEXT_EXCEEDED

    def test_is_content_policy_violation_scans_body_when_message_is_empty(self) -> None:
        """Azure REST puts safety phrasing only in the response body; the message stays the
        ``HTTPStatusError`` envelope. The probe must still detect the violation by scanning
        the in-process ``body`` field.
        """
        metadata = ProviderErrorMetadata(
            provider=ProviderName.AZURE,
            sdk_exception_type="HTTPStatusError",
            message="Client error '400 Bad Request' for url 'https://test.azure.com'",
            status_code=400,
            body={"error": {"code": "content_filter", "message": "Your prompt was blocked"}},
        )

        assert metadata.is_content_policy_violation is True

    def test_is_content_policy_violation_with_raw_string_body(self) -> None:
        """Body may also be a raw string when JSON parsing fails (e.g. HTML error page)."""
        metadata = ProviderErrorMetadata(
            provider=ProviderName.AZURE,
            sdk_exception_type="HTTPStatusError",
            message="Client error",
            status_code=400,
            body="Blocked by safety filter",
        )

        assert metadata.is_content_policy_violation is True

    @pytest.mark.parametrize(
        ("_topic", "sdk_exception_type", "status_code", "expected"),
        [
            ("connection_error_no_status", "APIConnectionError", None, True),
            ("timeout_no_status", "APITimeoutError", None, True),
            ("transport_no_status", "TransportError", None, True),
            ("validation_error_no_status", "ValidationError", None, False),
            ("connection_error_with_status", "APIConnectionError", 500, False),
        ],
    )
    def test_is_network_error(
        self,
        _topic: str,
        sdk_exception_type: str,
        status_code: int | None,
        expected: bool,
    ) -> None:
        metadata = ProviderErrorMetadata(
            provider=ProviderName.OPENAI,
            sdk_exception_type=sdk_exception_type,
            status_code=status_code,
        )

        assert metadata.is_network_error is expected
