"""Test data for FAL worker error handling tests."""

from typing import ClassVar

from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind


class FalErrorHandlingTestData:
    """Test cases for FAL ImgGen worker SDK exception handling.

    Each tuple: (topic, status_code, message, expected_category, expected_user_action_kind)
    """

    HTTP_ERROR_CASES: ClassVar[list[tuple[str, int, str, InferenceErrorCategory, UserActionKind]]] = [
        (
            "rate_limit_429",
            429,
            "Too many requests",
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
        ),
        (
            "quota_exhausted_402",
            402,
            "Payment required - quota exhausted",
            InferenceErrorCategory.CAPACITY,
            UserActionKind.CHECK_BILLING,
        ),
        (
            "auth_error_401",
            401,
            "Invalid API key",
            InferenceErrorCategory.CONFIGURATION,
            UserActionKind.CHECK_CREDENTIALS,
        ),
        (
            "forbidden_403",
            403,
            "Access denied",
            InferenceErrorCategory.CONFIGURATION,
            UserActionKind.CHECK_CREDENTIALS,
        ),
        (
            "bad_request_400",
            400,
            "Invalid parameter",
            InferenceErrorCategory.CONTENT,
            UserActionKind.CHANGE_INPUT,
        ),
        (
            "server_error_500",
            500,
            "Internal server error",
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
        ),
    ]

    MISSING_CREDENTIALS_CASES: ClassVar[list[tuple[str, InferenceErrorCategory, UserActionKind]]] = [
        (
            "missing_fal_key",
            InferenceErrorCategory.CONFIGURATION,
            UserActionKind.CHECK_CREDENTIALS,
        ),
    ]

    TIMEOUT_CASES: ClassVar[list[tuple[str, InferenceErrorCategory, UserActionKind]]] = [
        (
            "request_timeout",
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
        ),
    ]

    GENERIC_CLIENT_ERROR_CASES: ClassVar[list[tuple[str, InferenceErrorCategory, UserActionKind]]] = [
        (
            "generic_fal_error",
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
        ),
    ]
