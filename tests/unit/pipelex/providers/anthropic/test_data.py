"""Test data for Anthropic worker error handling tests."""

from typing import ClassVar

from pipelex.cogt.exceptions import InferenceErrorCategory


class AnthropicErrorHandlingTestData:
    """Test cases for Anthropic worker SDK exception handling.

    Each tuple: (topic, error_message, expected_category, expected_user_action_substring_or_none)
    """

    RATE_LIMIT_CASES: ClassVar[list[tuple[str, str, InferenceErrorCategory, str | None]]] = [
        (
            "generic_rate_limit",
            "rate_limit_error: Number of request tokens has exceeded your per-minute limit",
            InferenceErrorCategory.TRANSIENT,
            "retry",
        ),
        (
            "quota_exhaustion",
            "Your account quota has been exceeded",
            InferenceErrorCategory.CAPACITY,
            "billing",
        ),
        (
            "billing_limit",
            "You have reached your billing limit",
            InferenceErrorCategory.CAPACITY,
            "billing",
        ),
    ]

    BAD_REQUEST_CASES: ClassVar[list[tuple[str, str, InferenceErrorCategory, str | None]]] = [
        (
            "generic_bad_request",
            "Invalid parameter: max_tokens must be positive",
            InferenceErrorCategory.CONTENT,
            None,
        ),
        (
            "content_policy",
            "Your request was rejected due to content_policy_violation",
            InferenceErrorCategory.CONTENT,
            "safety filters",
        ),
    ]
