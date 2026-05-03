"""Test data for HuggingFace worker error handling tests."""

from typing import ClassVar

from pipelex.cogt.exceptions import InferenceErrorCategory


class HuggingFaceErrorHandlingTestData:
    """Test cases for HuggingFace ImgGen worker SDK exception handling.

    Each tuple: (topic, status_code_or_none, message, expected_category, expected_message_substring)
    """

    HF_HTTP_ERROR_CASES: ClassVar[list[tuple[str, int | None, str, InferenceErrorCategory, str]]] = [
        (
            "rate_limit_429",
            429,
            "Rate limit exceeded",
            InferenceErrorCategory.TRANSIENT,
            "rate limit",
        ),
        (
            "quota_exhausted_402",
            402,
            "Quota exhausted",
            InferenceErrorCategory.CAPACITY,
            "quota",
        ),
        (
            "auth_error_401",
            401,
            "Invalid token",
            InferenceErrorCategory.CONFIGURATION,
            "authentication error",
        ),
        (
            "forbidden_403",
            403,
            "Access denied",
            InferenceErrorCategory.CONFIGURATION,
            "authentication error",
        ),
        (
            "bad_request_400",
            400,
            "Invalid parameters",
            InferenceErrorCategory.CONTENT,
            "bad request",
        ),
        (
            "unknown_status_none",
            None,
            "Unknown error occurred",
            InferenceErrorCategory.TRANSIENT,
            "api error",
        ),
        (
            "server_error_503",
            503,
            "Service unavailable",
            InferenceErrorCategory.TRANSIENT,
            "api error",
        ),
    ]

    TIMEOUT_CASES: ClassVar[list[tuple[str, InferenceErrorCategory, str]]] = [
        (
            "inference_timeout",
            InferenceErrorCategory.TRANSIENT,
            "timed out",
        ),
    ]
