"""Test data for Anthropic worker error handling tests."""

from typing import Any, ClassVar

from pipelex.cogt.exceptions import InferenceErrorCategory
from tests.unit.pipelex.cogt.test_data import DirectProviderQuotaTestData


class AnthropicErrorHandlingTestData:
    """Test cases for Anthropic worker SDK exception handling.

    Each tuple: (topic, error_message, expected_category, expected_user_action_substring_or_none), the rate-limit
    cases carrying the error body after the message.
    """

    # (topic, error_message, body, expected_category, expected_user_action_substring_or_none): a 429 is a spent quota
    # on the spend cap's code in its body alone, whatever its words say
    RATE_LIMIT_CASES: ClassVar[list[tuple[str, str, dict[str, Any] | None, InferenceErrorCategory, str | None]]] = [
        (
            "generic_rate_limit",
            "rate_limit_error: Number of request tokens has exceeded your per-minute limit",
            DirectProviderQuotaTestData.ANTHROPIC_RATE_LIMIT_BODY,
            InferenceErrorCategory.TRANSIENT,
            "run it again",
        ),
        (
            "quota_wording_without_the_spend_cap_code",
            "Your account quota has been exceeded",
            None,
            InferenceErrorCategory.TRANSIENT,
            "run it again",
        ),
        (
            "monthly_spend_cap",
            "You have reached your API usage limits",
            DirectProviderQuotaTestData.ANTHROPIC_SPEND_CAP_BODY,
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
