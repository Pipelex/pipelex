"""Test data for HuggingFace worker error handling tests."""

from typing import ClassVar

from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind


class HuggingFaceErrorHandlingTestData:
    """Test cases for HuggingFace ImgGen worker SDK exception handling.

    Each tuple: (topic, status_code_or_none, message, expected_category, expected_user_action_kind)
    """

    HF_HTTP_ERROR_CASES: ClassVar[list[tuple[str, int | None, str, InferenceErrorCategory, UserActionKind]]] = [
        (
            "rate_limit_429",
            429,
            "Rate limit exceeded",
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
        ),
        (
            "quota_exhausted_402",
            402,
            "Quota exhausted",
            InferenceErrorCategory.CAPACITY,
            UserActionKind.CHECK_BILLING,
        ),
        (
            "auth_error_401",
            401,
            "Invalid token",
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
            "Invalid parameters",
            InferenceErrorCategory.CONTENT,
            UserActionKind.CHANGE_INPUT,
        ),
        (
            # An HfHubHTTPError without an HTTP status is statusless from the classifier's
            # point of view; the unified classifier maps it to UNKNOWN/CONTACT_SUPPORT.
            "unknown_status_none",
            None,
            "Unknown error occurred",
            InferenceErrorCategory.UNKNOWN,
            UserActionKind.CONTACT_SUPPORT,
        ),
        (
            "server_error_503",
            503,
            "Service unavailable",
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
        ),
    ]

    TIMEOUT_CASES: ClassVar[list[tuple[str, InferenceErrorCategory, UserActionKind]]] = [
        (
            "inference_timeout",
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
        ),
    ]
