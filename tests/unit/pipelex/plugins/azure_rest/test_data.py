"""Test data for Azure REST worker error handling tests."""

from typing import ClassVar

from pipelex.cogt.exceptions import InferenceErrorCategory


class AzureErrorHandlingTestData:
    """Test cases for Azure ImgGen worker HTTP exception handling.

    Each tuple: (topic, status_code, response_text, expected_category, expected_message_substring)
    """

    HTTP_STATUS_ERROR_CASES: ClassVar[list[tuple[str, int, str, InferenceErrorCategory, str]]] = [
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
            "Quota exhausted for this subscription",
            InferenceErrorCategory.CAPACITY,
            "quota",
        ),
        (
            "auth_error_401",
            401,
            "Invalid subscription key",
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
            "Invalid parameter value",
            InferenceErrorCategory.CONTENT,
            "bad request",
        ),
        (
            # A 5xx is returned after the request reached Azure — Azure may have generated (and
            # billed) the image — so for a non-idempotent image submit it is categorized
            # AMBIGUOUS (non-retryable), consistent with mid-request timeout handling.
            "server_error_500",
            500,
            "Internal server error",
            InferenceErrorCategory.AMBIGUOUS,
            "server error",
        ),
    ]

    CONNECT_ERROR_CASES: ClassVar[list[tuple[str, InferenceErrorCategory, str]]] = [
        (
            "connection_refused",
            InferenceErrorCategory.TRANSIENT,
            "connection error",
        ),
    ]

    TIMEOUT_ERROR_CASES: ClassVar[list[tuple[str, InferenceErrorCategory, str]]] = [
        (
            # A ReadTimeout fires after the request reached Azure — the outcome is ambiguous on a
            # non-idempotent image submit, so it is categorized AMBIGUOUS (non-retryable).
            "read_timeout",
            InferenceErrorCategory.AMBIGUOUS,
            "timed out",
        ),
    ]
