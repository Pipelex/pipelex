"""Tests for quota and content-policy detection on ``ProviderErrorMetadata``.

The quota and content-policy probes are exposed via the
``ProviderErrorMetadata.is_quota_exhaustion`` / ``is_content_policy_violation``
properties; the helpers backing them are module-private. These tests pin the
per-provider phrase matching so changes to the patterns surface as test diffs.
"""

from typing import ClassVar

import pytest

from pipelex.cogt.inference.error_classification import ProviderErrorMetadata
from pipelex.cogt.inference.provider_name import ProviderName


def _metadata(provider: ProviderName, message: str, status_code: int | None = None) -> ProviderErrorMetadata:
    return ProviderErrorMetadata(
        provider=provider,
        sdk_exception_type="RateLimitError",
        message=message,
        status_code=status_code,
    )


class _TestCases:
    # (topic, message, expected_is_quota)
    OPENAI_QUOTA_CASES: ClassVar[list[tuple[str, str, bool]]] = [
        ("insufficient_quota", "Error: insufficient_quota - you have exceeded your billing limit", True),
        ("exceeded_quota", "You exceeded your current quota, please check your plan", True),
        ("generic_rate_limit", "Rate limit exceeded. Please retry after 20s", False),
        ("empty_message", "", False),
        ("unrelated_error", "Invalid API key provided", False),
        ("case_insensitive", "Insufficient_Quota error occurred", True),
    ]

    ANTHROPIC_QUOTA_CASES: ClassVar[list[tuple[str, str, bool]]] = [
        ("quota_in_message", "Your account quota has been exceeded", True),
        ("billing_limit", "You have reached your billing limit", True),
        ("billing_issue", "There is a billing issue with your account", True),
        ("credit_balance", "Your credit balance is too low to make this request", True),
        ("out_of_credits", "Account is out of credits", True),
        ("insufficient_credit", "Insufficient credit on this API key", True),
        ("generic_rate_limit", "rate_limit_error: Number of request tokens has exceeded your per-minute limit", False),
        ("empty_message", "", False),
        ("unrelated_error", "Invalid API key", False),
        ("billing_word_alone_not_matched", "Please check your billing dashboard", False),
        ("credit_card_declined_not_matched", "Your credit card was declined, please update payment method", False),
        ("credit_account_not_matched", "We will credit your account within 24 hours", False),
        ("no_credit_check_not_matched", "No credit check required", False),
        ("case_insensitive", "Account Billing Issue detected", True),
    ]

    GOOGLE_QUOTA_CASES: ClassVar[list[tuple[str, str, bool]]] = [
        ("quota_exceeded", "Quota exceeded for aiplatform.googleapis.com", True),
        ("resource_exhausted", "Resource has been exhausted (e.g. check quota)", True),
        ("billing_quota_exceeded", "Billing quota exceeded for project foo", True),
        ("billing_limit_reached", "Billing limit reached on this account", True),
        ("billing_exceeded", "Billing exceeded for the current period", True),
        ("billing_account_not_active", "Billing account is not active", True),
        ("billing_account_disabled", "billing account is disabled for project", True),
        ("generic_rate_limit", "Rate limit exceeded per minute", False),
        ("empty_message", "", False),
        ("unrelated_error", "Model not found", False),
        ("billing_setup_not_quota", "billing project not configured", False),
        ("billing_enable_not_quota", "Please enable billing for this project to use this API", False),
        ("billing_api_not_enabled_not_quota", "billing API not enabled", False),
    ]

    # (topic, message, status_code, expected_is_quota)
    MISTRAL_QUOTA_CASES: ClassVar[list[tuple[str, str, int, bool]]] = [
        ("payment_required_402", "Payment required", 402, True),
        ("quota_429", "Quota exceeded for your account", 429, True),
        ("billing_429", "Billing limit reached", 429, True),
        ("generic_rate_limit_429", "Rate limit exceeded. Please retry after 20s", 429, False),
        ("server_error_500", "Internal server error", 500, False),
        ("not_found_404", "Model not found", 404, False),
        ("payment_required_402_any_message", "anything at all", 402, True),
    ]

    AWS_QUOTA_CASES: ClassVar[list[tuple[str, str, bool]]] = [
        ("quota_exceeded", "Service quota exceeded for this account", True),
        ("limit_exceeded", "Token limit exceeded for model", True),
        ("generic_throttle", "Rate exceeded", False),
        ("empty_message", "", False),
        ("unrelated_error", "Access denied", False),
    ]

    # (topic, message, status_code, expected_is_quota)
    GATEWAY_QUOTA_CASES: ClassVar[list[tuple[str, str, int, bool]]] = [
        ("payment_required_402", "Payment required", 402, True),
        ("quota_429", "Your quota has been exhausted", 429, True),
        ("billing_429", "Billing limit exceeded", 429, True),
        ("insufficient_credits_429", "Insufficient credits", 429, True),
        ("insufficient_quota_429", "insufficient_quota for this account", 429, True),
        ("insufficient_funds_429", "Insufficient funds in your account", 429, True),
        ("insufficient_balance_429", "Insufficient balance to complete request", 429, True),
        ("credits_exhausted_429", "Credits exhausted on this key", 429, True),
        ("insufficient_permissions_429_not_quota", "Insufficient permissions to use this model", 429, False),
        ("insufficient_role_429_not_quota", "Insufficient role for the requested action", 429, False),
        ("insufficient_access_429_not_quota", "Insufficient access privileges", 429, False),
        ("generic_rate_limit_429", "Rate limit exceeded. Please retry", 429, False),
        ("server_error_500", "Internal server error", 500, False),
        ("payment_required_402_any_message", "random text", 402, True),
    ]

    CONTENT_POLICY_CASES: ClassVar[list[tuple[str, str, bool]]] = [
        ("content_policy", "Your request was rejected due to content_policy_violation", True),
        ("blocked_by_safety", "The response was blocked by safety systems", True),
        ("content_filter", "content_filter triggered for this request", True),
        ("safety_system", "Rejected by safety system", True),
        ("safety_filter", "Blocked by safety filter", True),
        ("generic_bad_request", "Invalid parameter: temperature must be between 0 and 2", False),
        ("empty_message", "", False),
        ("safety_word_alone_not_matched", "Please ensure thread safety when using this", False),
        ("case_insensitive", "Content_Policy violation detected", True),
    ]


class TestErrorClassification:
    """Tests for quota detection and content policy classification via the public ``ProviderErrorMetadata`` properties."""

    @pytest.mark.parametrize(
        ("_topic", "error_message", "expected"),
        _TestCases.OPENAI_QUOTA_CASES,
    )
    def test_is_quota_exhaustion_openai(self, _topic: str, error_message: str, expected: bool) -> None:
        """Discriminate OpenAI quota exhaustion from generic rate limiting."""
        assert _metadata(ProviderName.OPENAI, error_message).is_quota_exhaustion == expected

    @pytest.mark.parametrize(
        ("_topic", "error_message", "expected"),
        _TestCases.ANTHROPIC_QUOTA_CASES,
    )
    def test_is_quota_exhaustion_anthropic(self, _topic: str, error_message: str, expected: bool) -> None:
        """Discriminate Anthropic quota exhaustion from generic rate limiting."""
        assert _metadata(ProviderName.ANTHROPIC, error_message).is_quota_exhaustion == expected

    @pytest.mark.parametrize(
        ("_topic", "error_message", "expected"),
        _TestCases.CONTENT_POLICY_CASES,
    )
    def test_is_content_policy_violation(self, _topic: str, error_message: str, expected: bool) -> None:
        """Detect content policy and safety filter violations (provider-agnostic)."""
        assert _metadata(ProviderName.OPENAI, error_message).is_content_policy_violation == expected

    @pytest.mark.parametrize(
        ("_topic", "error_message", "expected"),
        _TestCases.GOOGLE_QUOTA_CASES,
    )
    def test_is_quota_exhaustion_google(self, _topic: str, error_message: str, expected: bool) -> None:
        """Discriminate Google quota exhaustion from generic rate limiting."""
        assert _metadata(ProviderName.GOOGLE, error_message).is_quota_exhaustion == expected

    @pytest.mark.parametrize(
        ("_topic", "error_message", "status_code", "expected"),
        _TestCases.MISTRAL_QUOTA_CASES,
    )
    def test_is_quota_exhaustion_mistral(self, _topic: str, error_message: str, status_code: int, expected: bool) -> None:
        """Discriminate Mistral quota exhaustion from generic rate limiting."""
        assert _metadata(ProviderName.MISTRAL, error_message, status_code).is_quota_exhaustion == expected

    @pytest.mark.parametrize(
        ("_topic", "error_message", "expected"),
        _TestCases.AWS_QUOTA_CASES,
    )
    def test_is_quota_exhaustion_aws(self, _topic: str, error_message: str, expected: bool) -> None:
        """Discriminate AWS quota exhaustion from generic throttling."""
        assert _metadata(ProviderName.BEDROCK, error_message).is_quota_exhaustion == expected

    @pytest.mark.parametrize(
        ("_topic", "error_message", "status_code", "expected"),
        _TestCases.GATEWAY_QUOTA_CASES,
    )
    def test_is_quota_exhaustion_gateway(self, _topic: str, error_message: str, status_code: int, expected: bool) -> None:
        """Discriminate Gateway quota exhaustion from generic rate limiting."""
        assert _metadata(ProviderName.GATEWAY, error_message, status_code).is_quota_exhaustion == expected
