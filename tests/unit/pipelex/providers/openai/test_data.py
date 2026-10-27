"""Test data for OpenAI worker error handling tests."""

from typing import Any, ClassVar

from pipelex.cogt.exceptions import InferenceErrorCategory
from tests.unit.pipelex.cogt.test_data import DirectProviderQuotaTestData


class OpenAIErrorHandlingTestData:
    """Test cases for OpenAI worker SDK exception handling.

    Each tuple: (topic, error_message, expected_category, expected_user_action_substring_or_none), the rate-limit
    cases carrying the error body after the message.
    """

    # (topic, error_message, body, expected_category, expected_user_action_substring_or_none), the body being the error
    # section the OpenAI client keeps: a 429 is a spent quota on OpenAI's quota code or type alone, whatever its words
    RATE_LIMIT_CASES: ClassVar[list[tuple[str, str, dict[str, Any] | None, InferenceErrorCategory, str | None]]] = [
        (
            "generic_rate_limit",
            "Rate limit exceeded. Please retry after 20s",
            DirectProviderQuotaTestData.OPENAI_RATE_LIMIT_BODY["error"],
            InferenceErrorCategory.TRANSIENT,
            "run it again",
        ),
        (
            "quota_insufficient",
            "Error: insufficient_quota - you have exceeded your billing limit",
            DirectProviderQuotaTestData.OPENAI_INSUFFICIENT_QUOTA_BODY["error"],
            InferenceErrorCategory.CAPACITY,
            "billing",
        ),
        (
            "billing_code_beside_the_broad_type",
            "Your organization has no prepaid credits remaining.",
            DirectProviderQuotaTestData.OPENAI_CREDIT_BALANCE_EXHAUSTED_BODY["error"],
            InferenceErrorCategory.CAPACITY,
            "billing",
        ),
        (
            "quota_wording_without_a_quota_code",
            "You exceeded your current quota, please check your plan",
            None,
            InferenceErrorCategory.TRANSIENT,
            "run it again",
        ),
    ]

    TIMEOUT_CASES: ClassVar[list[tuple[str, str, InferenceErrorCategory]]] = [
        (
            "api_timeout",
            "Request timed out",
            InferenceErrorCategory.TRANSIENT,
        ),
    ]

    BAD_REQUEST_CASES: ClassVar[list[tuple[str, str, InferenceErrorCategory, str | None]]] = [
        (
            "generic_bad_request",
            "Invalid parameter: temperature must be between 0 and 2",
            InferenceErrorCategory.CONTENT,
            None,
        ),
        (
            "content_policy",
            "Your request was rejected due to content_policy_violation",
            InferenceErrorCategory.CONTENT,
            "safety filters",
        ),
        (
            "blocked_by_safety",
            "The response was blocked by safety systems",
            InferenceErrorCategory.CONTENT,
            "safety filters",
        ),
    ]


class GatewayStopTestData:
    """Stop values a gateway in non-strict mode passes through the chat-completions shape in each provider's vocabulary.

    Each tuple: (topic, finish_reason, content); the content is partial or empty, as the gateway sets it.
    """

    TRUNCATION_CASES: ClassVar[list[tuple[str, str, str]]] = [
        ("claude cut at max_tokens", "max_tokens", "The contract binds the parties to"),
        ("claude cut with nothing written", "max_tokens", ""),
        ("gemini cut at max_tokens", "MAX_TOKENS", "The contract binds the parties to"),
        ("strict mode cut", "length", "The contract binds the parties to"),
    ]

    REFUSAL_CASES: ClassVar[list[tuple[str, str, str]]] = [
        ("bedrock content filter", "content_filtered", ""),
        ("claude refusal", "refusal", ""),
        ("gemini safety stop after partial text", "SAFETY", "The contract binds the parties to"),
    ]
