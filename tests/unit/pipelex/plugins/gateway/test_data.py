"""Test data for Gateway worker error handling and quota detection tests."""

from typing import ClassVar

from pipelex.cogt.exceptions import InferenceErrorCategory


class GatewayQuotaDetectionTestData:
    """Test cases for Portkey error classification across gateway workers.

    CLASSIFY_CASES tuple: (topic, exception_type_name, status_code, error_message, expected_category)
    The exception_type_name is used to select which portkey exception to construct.
    """

    CLASSIFY_CASES: ClassVar[list[tuple[str, str, int, str, InferenceErrorCategory]]] = [
        (
            "rate_limit_transient",
            "RateLimitError",
            429,
            "Rate limit exceeded. Please retry after 20s",
            InferenceErrorCategory.TRANSIENT,
        ),
        (
            "rate_limit_quota_keyword",
            "RateLimitError",
            429,
            "You have exceeded your quota allocation",
            InferenceErrorCategory.CAPACITY,
        ),
        (
            "rate_limit_billing_keyword",
            "RateLimitError",
            429,
            "Billing limit reached",
            InferenceErrorCategory.CAPACITY,
        ),
        (
            "payment_required_402",
            "APIStatusError",
            402,
            "Payment required",
            InferenceErrorCategory.CAPACITY,
        ),
        (
            "auth_error_401",
            "AuthenticationError",
            401,
            "Invalid API key",
            InferenceErrorCategory.CONFIGURATION,
        ),
        (
            "permission_denied_403",
            "PermissionDeniedError",
            403,
            "Access denied",
            InferenceErrorCategory.CONFIGURATION,
        ),
        (
            "bad_request_400",
            "BadRequestError",
            400,
            "Invalid parameters",
            InferenceErrorCategory.CONTENT,
        ),
        (
            "not_found_404",
            "NotFoundError",
            404,
            "Model not found",
            InferenceErrorCategory.CONFIGURATION,
        ),
        (
            "not_found_404_deployment_propagation_race",
            "NotFoundError",
            404,
            "The specified deployment could not be found",
            InferenceErrorCategory.TRANSIENT,
        ),
        (
            "timeout_error",
            "APITimeoutError",
            0,
            "Request timed out",
            InferenceErrorCategory.TRANSIENT,
        ),
        (
            "connection_error",
            "APIConnectionError",
            0,
            "Connection refused",
            InferenceErrorCategory.TRANSIENT,
        ),
    ]
