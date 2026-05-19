"""Test data for Azure REST worker error handling tests."""

from typing import ClassVar

from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind


class AzureErrorHandlingTestData:
    """Test cases for Azure ImgGen worker HTTP exception handling.

    Each tuple: (topic, status_code, response_text, expected_category, expected_user_action_kind)
    """

    HTTP_STATUS_ERROR_CASES: ClassVar[list[tuple[str, int, str, InferenceErrorCategory, UserActionKind]]] = [
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
            "Quota exhausted for this subscription",
            InferenceErrorCategory.CAPACITY,
            UserActionKind.CHECK_BILLING,
        ),
        (
            "auth_error_401",
            401,
            "Invalid subscription key",
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
            "Invalid parameter value",
            InferenceErrorCategory.CONTENT,
            UserActionKind.CHANGE_INPUT,
        ),
        (
            # A 5xx is returned after the request reached Azure — Azure may have generated (and
            # billed) the image — so for a non-idempotent image submit it is categorized
            # AMBIGUOUS (non-retryable), consistent with mid-request timeout handling.
            "server_error_500",
            500,
            "Internal server error",
            InferenceErrorCategory.AMBIGUOUS,
            UserActionKind.WAIT_AND_RETRY,
        ),
    ]

    CONNECT_ERROR_CASES: ClassVar[list[tuple[str, InferenceErrorCategory, UserActionKind]]] = [
        (
            "connection_refused",
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
        ),
    ]

    TIMEOUT_ERROR_CASES: ClassVar[list[tuple[str, InferenceErrorCategory, UserActionKind]]] = [
        (
            # A ReadTimeout fires after the request reached Azure — the outcome is ambiguous on a
            # non-idempotent image submit, so it is categorized AMBIGUOUS (non-retryable).
            "read_timeout",
            InferenceErrorCategory.AMBIGUOUS,
            UserActionKind.WAIT_AND_RETRY,
        ),
    ]
