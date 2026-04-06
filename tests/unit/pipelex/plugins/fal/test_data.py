"""Test data for FAL worker error handling tests."""

from typing import ClassVar

from pipelex.cogt.exceptions import InferenceErrorCategory


class FalErrorHandlingTestData:
    """Test cases for FAL ImgGen worker SDK exception handling.

    Each tuple: (topic, status_code, message, expected_category, expected_message_substring)
    """

    HTTP_ERROR_CASES: ClassVar[list[tuple[str, int, str, InferenceErrorCategory, str]]] = [
        (
            "rate_limit_429",
            429,
            "Too many requests",
            InferenceErrorCategory.TRANSIENT,
            "rate limit",
        ),
        (
            "quota_exhausted_402",
            402,
            "Payment required - quota exhausted",
            InferenceErrorCategory.CAPACITY,
            "quota",
        ),
        (
            "auth_error_401",
            401,
            "Invalid API key",
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
            "Invalid parameter",
            InferenceErrorCategory.CONTENT,
            "bad request",
        ),
        (
            "server_error_500",
            500,
            "Internal server error",
            InferenceErrorCategory.TRANSIENT,
            "api error",
        ),
    ]

    MISSING_CREDENTIALS_CASES: ClassVar[list[tuple[str, InferenceErrorCategory, str]]] = [
        (
            "missing_fal_key",
            InferenceErrorCategory.CONFIGURATION,
            "fal api key",
        ),
    ]

    TIMEOUT_CASES: ClassVar[list[tuple[str, InferenceErrorCategory, str]]] = [
        (
            "request_timeout",
            InferenceErrorCategory.TRANSIENT,
            "timed out",
        ),
    ]

    GENERIC_CLIENT_ERROR_CASES: ClassVar[list[tuple[str, InferenceErrorCategory, str]]] = [
        (
            "generic_fal_error",
            InferenceErrorCategory.TRANSIENT,
            "fal error",
        ),
    ]
