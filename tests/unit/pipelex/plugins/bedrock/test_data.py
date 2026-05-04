"""Test data for Bedrock worker error handling tests."""

from typing import ClassVar

from pipelex.cogt.exceptions import InferenceErrorCategory


class BedrockLLMErrorHandlingTestData:
    """Test cases for Bedrock LLM worker ClientError exception handling.

    Each tuple: (topic, error_code, error_message, expected_category, expected_user_action_substring_or_none)
    """

    CLIENT_ERROR_CASES: ClassVar[list[tuple[str, str, str, InferenceErrorCategory, str | None]]] = [
        (
            "throttling_generic",
            "ThrottlingException",
            "Rate exceeded for model",
            InferenceErrorCategory.TRANSIENT,
            "retry",
        ),
        (
            "throttling_quota",
            "ThrottlingException",
            "Account quota limit exceeded for this model",
            InferenceErrorCategory.CAPACITY,
            "billing",
        ),
        (
            "service_quota_exceeded",
            "ServiceQuotaExceededException",
            "You have exceeded the service quota for this resource",
            InferenceErrorCategory.CAPACITY,
            "billing",
        ),
        (
            "access_denied",
            "AccessDeniedException",
            "User is not authorized to access this model",
            InferenceErrorCategory.CONFIGURATION,
            None,
        ),
        (
            "validation_exception",
            "ValidationException",
            "Invalid parameter: max_tokens must be positive",
            InferenceErrorCategory.CONTENT,
            None,
        ),
        (
            "model_not_ready",
            "ModelNotReadyException",
            "Model is not ready for inference",
            InferenceErrorCategory.TRANSIENT,
            None,
        ),
        (
            "service_unavailable",
            "ServiceUnavailableException",
            "Service is temporarily unavailable",
            InferenceErrorCategory.TRANSIENT,
            None,
        ),
    ]
