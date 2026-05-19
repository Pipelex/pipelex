"""Tests for the ``ProviderErrorMetadata`` Pydantic model.

This model carries structured SDK metadata alongside every inference error so
downstream consumers (retry / temporal / CLI) do not have to scrape it back
from the exception chain.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipelex.cogt.inference.error_classification import ProviderErrorMetadata
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
            ("openai_quota", ProviderName.OPENAI, "You exceeded your current quota", None, None, True),
            ("openai_rate_limit", ProviderName.OPENAI, "Rate limit reached", None, None, False),
            ("anthropic_credit_balance", ProviderName.ANTHROPIC, "Your credit balance is too low", None, None, True),
            ("mistral_402_is_quota", ProviderName.MISTRAL, "payment required", 402, None, True),
            ("mistral_429_quota_pattern", ProviderName.MISTRAL, "quota exceeded", 429, None, True),
            ("mistral_429_plain_rate_limit", ProviderName.MISTRAL, "too many requests", 429, None, False),
            ("gateway_402_is_quota", ProviderName.GATEWAY, "payment required", 402, None, True),
            ("azure_never_quota", ProviderName.AZURE, "quota exceeded", 429, None, False),
            (
                "bedrock_quota_by_aws_code_no_message_hint",
                ProviderName.BEDROCK,
                "An error occurred",
                400,
                "ServiceQuotaExceededException",
                True,
            ),
            (
                "bedrock_quota_message_keyword",
                ProviderName.BEDROCK,
                "Service quota exceeded for this model",
                400,
                None,
                True,
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
