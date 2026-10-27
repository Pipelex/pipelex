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
            "run it again",
        ),
        # Bedrock has no balance to spend: a throttle is a rate limit whatever its words, and AWS documents
        # `ServiceQuotaExceededException` as resubmittable later
        (
            "throttling_with_quota_wording",
            "ThrottlingException",
            "Account quota limit exceeded for this model",
            InferenceErrorCategory.TRANSIENT,
            "run it again",
        ),
        (
            "service_quota_exceeded",
            "ServiceQuotaExceededException",
            "You have exceeded the service quota for this resource",
            InferenceErrorCategory.TRANSIENT,
            "run it again",
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
