"""Test data for Mistral worker error handling tests."""

from typing import ClassVar

from pipelex.cogt.exceptions import InferenceErrorCategory


class MistralLLMErrorHandlingTestData:
    """Test cases for Mistral LLM worker SDK exception handling.

    Each tuple: (topic, status_code, error_message, expected_category, expected_user_action_substring_or_none)
    """

    SDK_ERROR_CASES: ClassVar[list[tuple[str, int, str, InferenceErrorCategory, str | None]]] = [
        (
            "payment_required_402",
            402,
            "Payment required: insufficient credits",
            InferenceErrorCategory.CAPACITY,
            "billing",
        ),
        (
            "rate_limit_quota_429",
            429,
            "Rate limit reached: your account quota has been exceeded",
            InferenceErrorCategory.CAPACITY,
            "billing",
        ),
        (
            "rate_limit_generic_429",
            429,
            "Rate limit exceeded. Please retry after 20s",
            InferenceErrorCategory.TRANSIENT,
            "retry",
        ),
        (
            "auth_error_401",
            401,
            "Invalid API key provided",
            InferenceErrorCategory.CONFIGURATION,
            None,
        ),
        (
            "forbidden_403",
            403,
            "You do not have access to this resource",
            InferenceErrorCategory.CONFIGURATION,
            None,
        ),
        (
            "model_not_found_404",
            404,
            "Model mistral-unknown not found",
            InferenceErrorCategory.CONFIGURATION,
            None,
        ),
        (
            "bad_request_content_policy_400",
            400,
            "Your request was rejected due to content_policy_violation",
            InferenceErrorCategory.CONTENT,
            "safety filters",
        ),
        (
            "bad_request_generic_400",
            400,
            "Invalid parameter: temperature must be between 0 and 1",
            InferenceErrorCategory.CONTENT,
            None,
        ),
        (
            "server_error_500",
            500,
            "Internal server error",
            InferenceErrorCategory.TRANSIENT,
            None,
        ),
    ]


class MistralExtractErrorHandlingTestData:
    """Test cases for Mistral Extract worker SDK exception handling.

    Each tuple: (topic, status_code, error_message, expected_category, expected_user_action_substring_or_none)
    """

    SDK_ERROR_CASES: ClassVar[list[tuple[str, int, str, InferenceErrorCategory, str | None]]] = [
        (
            "payment_required_402",
            402,
            "Payment required: insufficient credits",
            InferenceErrorCategory.CAPACITY,
            "billing",
        ),
        (
            "rate_limit_quota_429",
            429,
            "Rate limit reached: your account quota has been exceeded",
            InferenceErrorCategory.CAPACITY,
            "billing",
        ),
        (
            "rate_limit_generic_429",
            429,
            "Rate limit exceeded. Please retry after 20s",
            InferenceErrorCategory.TRANSIENT,
            "retry",
        ),
        (
            "auth_error_401",
            401,
            "Invalid API key provided",
            InferenceErrorCategory.CONFIGURATION,
            None,
        ),
        (
            "model_not_found_404",
            404,
            "Model mistral-ocr-unknown not found",
            InferenceErrorCategory.CONFIGURATION,
            None,
        ),
        (
            "bad_request_content_policy_400",
            400,
            "Your request was rejected due to content_policy_violation",
            InferenceErrorCategory.CONTENT,
            "safety filters",
        ),
        (
            "bad_request_generic_400",
            400,
            "Invalid parameter: unsupported document format",
            InferenceErrorCategory.CONTENT,
            None,
        ),
        (
            "server_error_503",
            503,
            "Service temporarily unavailable",
            InferenceErrorCategory.TRANSIENT,
            None,
        ),
    ]
