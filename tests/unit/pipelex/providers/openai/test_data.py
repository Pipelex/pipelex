"""Test data for OpenAI worker error handling tests."""

from typing import ClassVar

from pipelex.cogt.exceptions import InferenceErrorCategory


class OpenAIErrorHandlingTestData:
    """Test cases for OpenAI worker SDK exception handling.

    Each tuple: (topic, error_message, expected_category, expected_user_action_substring_or_none)
    """

    RATE_LIMIT_CASES: ClassVar[list[tuple[str, str, InferenceErrorCategory, str | None]]] = [
        (
            "generic_rate_limit",
            "Rate limit exceeded. Please retry after 20s",
            InferenceErrorCategory.TRANSIENT,
            "run it again",
        ),
        (
            "quota_insufficient",
            "Error: insufficient_quota - you have exceeded your billing limit",
            InferenceErrorCategory.CAPACITY,
            "billing",
        ),
        (
            "quota_exceeded",
            "You exceeded your current quota, please check your plan",
            InferenceErrorCategory.CAPACITY,
            "billing",
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
