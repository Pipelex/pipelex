"""Test data for Google worker error handling tests."""

from typing import ClassVar

from pipelex.cogt.exceptions import InferenceErrorCategory


class GoogleErrorHandlingTestData:
    """Test cases for Google worker SDK exception handling.

    Each tuple: (topic, status_code, error_message, expected_category, expected_user_action_substring_or_none)
    """

    # The 404 row is deliberately absent: both the LLM and the ImgGen workers specialize a 404
    # to a dedicated ``*ModelNotFoundError`` (not a plain completion/generation error), so the
    # 404 case is covered by its own dedicated test on each worker instead of this set.
    CLIENT_ERROR_CASES: ClassVar[list[tuple[str, int, str, InferenceErrorCategory, str | None]]] = [
        (
            "auth_401",
            401,
            "Request had invalid authentication credentials",
            InferenceErrorCategory.CONFIGURATION,
            None,
        ),
        (
            "forbidden_403",
            403,
            "Permission denied on resource project",
            InferenceErrorCategory.CONFIGURATION,
            None,
        ),
        (
            "rate_limit_429_quota",
            429,
            "Resource has been exhausted (e.g. check quota)",
            InferenceErrorCategory.CAPACITY,
            "billing",
        ),
        (
            "rate_limit_429_billing",
            429,
            "Billing account is not active",
            InferenceErrorCategory.CAPACITY,
            "billing",
        ),
        (
            "rate_limit_429_generic",
            429,
            "Too many requests, please slow down",
            InferenceErrorCategory.TRANSIENT,
            "retry",
        ),
        (
            "bad_request_400_content_policy",
            400,
            "Your request was rejected due to content_policy_violation",
            InferenceErrorCategory.CONTENT,
            "safety filters",
        ),
        (
            "bad_request_400_safety",
            400,
            "The response was blocked by safety systems",
            InferenceErrorCategory.CONTENT,
            "safety filters",
        ),
        (
            "bad_request_400_generic",
            400,
            "Invalid parameter: temperature must be between 0 and 2",
            InferenceErrorCategory.CONTENT,
            None,
        ),
        (
            "other_client_error_fallback",
            422,
            "Unprocessable entity",
            InferenceErrorCategory.CONFIGURATION,
            "review",
        ),
    ]
