"""Anthropic SDK error classification for the LLM worker.

Single entry point ``classify_anthropic_sdk_error`` returning a categorized
error (or ``None`` for an unrecognized exception type) so the caller controls
raising and ``raise ... from`` chaining.
"""

from anthropic import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError, LLMModelNotFoundError
from pipelex.cogt.inference.error_classification import (
    UserAction,
    UserActionKind,
    extract_anthropic_metadata,
    is_content_policy_violation,
    is_quota_exhaustion_anthropic,
)
from pipelex.plugins.anthropic.anthropic_exceptions import AnthropicCredentialsError
from pipelex.urls import URLs


def classify_anthropic_sdk_error(
    sdk_exc: BaseException,
    model_desc: str,
    model_id: str,
    model_handle: str,
) -> LLMCompletionError | AnthropicCredentialsError | LLMModelNotFoundError | None:
    """Build a categorized error from an Anthropic SDK exception.

    Returns ``None`` when ``sdk_exc`` is not a recognized Anthropic SDK
    exception type, so callers can apply their own fallback (e.g. an instructor
    exception whose underlying cause could not be recovered). ``AuthenticationError``
    yields the ``AnthropicCredentialsError`` specialization; ``NotFoundError``
    yields the ``LLMModelNotFoundError`` specialization.

    Args:
        sdk_exc: The exception to classify.
        model_desc: Human-readable model description for error messages.
        model_id: The provider-side model id.
        model_handle: The pipelex model handle, carried on ``LLMModelNotFoundError``.
    """
    if not isinstance(sdk_exc, (APIStatusError, APIConnectionError)):
        return None
    metadata = extract_anthropic_metadata(sdk_exc)

    if isinstance(sdk_exc, RateLimitError):
        error_message = str(sdk_exc)
        if is_quota_exhaustion_anthropic(error_message):
            msg = f"Anthropic quota exhausted for model '{model_desc}': {sdk_exc}"
            return LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CAPACITY,
                user_action=UserAction(
                    kind=UserActionKind.CHECK_BILLING,
                    detail=f"Your Anthropic account has exceeded its quota — check billing at {URLs.anthropic_billing}",
                ),
                provider_metadata=metadata,
            )
        msg = f"Anthropic rate limit exceeded for model '{model_desc}': {sdk_exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.TRANSIENT,
            user_action=UserAction(
                kind=UserActionKind.WAIT_AND_RETRY,
                detail="Rate limited by Anthropic — the system will retry automatically",
            ),
            provider_metadata=metadata,
        )

    if isinstance(sdk_exc, APITimeoutError):
        msg = f"Anthropic API request timed out for model '{model_desc}': {sdk_exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.TRANSIENT,
            user_action=UserAction(
                kind=UserActionKind.WAIT_AND_RETRY,
                detail="Anthropic API request timed out — the system will retry automatically",
            ),
            provider_metadata=metadata,
        )

    if isinstance(sdk_exc, BadRequestError):
        error_message = str(sdk_exc)
        if is_content_policy_violation(error_message):
            msg = f"Content rejected by safety filters for model '{model_desc}': {sdk_exc}"
            return LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="Content was rejected by safety filters — revise the prompt",
                ),
                provider_metadata=metadata,
            )
        msg = f"Anthropic bad request error: {sdk_exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.CONTENT,
            user_action=UserAction(
                kind=UserActionKind.CHANGE_INPUT,
                detail="Anthropic rejected the request — review the prompt and parameters",
            ),
            provider_metadata=metadata,
        )

    if isinstance(sdk_exc, APIConnectionError):
        msg = f"Anthropic API connection error: {sdk_exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.TRANSIENT,
            user_action=UserAction(
                kind=UserActionKind.WAIT_AND_RETRY,
                detail="Could not reach Anthropic — the system will retry automatically",
            ),
            provider_metadata=metadata,
        )

    if isinstance(sdk_exc, PermissionDeniedError):
        error_message = str(sdk_exc)
        if is_quota_exhaustion_anthropic(error_message):
            msg = f"Anthropic quota exhausted: {sdk_exc}"
            return LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CAPACITY,
                user_action=UserAction(
                    kind=UserActionKind.CHECK_BILLING,
                    detail=f"Your Anthropic account has exceeded its quota — check billing at {URLs.anthropic_billing}",
                ),
                provider_metadata=metadata,
            )
        msg = f"Anthropic permission denied: {sdk_exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.CONFIGURATION,
            user_action=UserAction(
                kind=UserActionKind.CHECK_CREDENTIALS,
                detail="Anthropic denied permission — check your API key permissions",
            ),
            provider_metadata=metadata,
        )

    if isinstance(sdk_exc, AuthenticationError):
        msg = f"Anthropic credentials error: {sdk_exc}"
        return AnthropicCredentialsError(msg, provider_metadata=metadata)

    if isinstance(sdk_exc, NotFoundError):
        msg = f"LLM model or deployment '{model_id}' not found: {sdk_exc}"
        return LLMModelNotFoundError(
            message=msg,
            model_handle=model_handle,
            error_category=InferenceErrorCategory.CONFIGURATION,
            user_action=UserAction(
                kind=UserActionKind.CHANGE_MODEL,
                detail=f"Model '{model_id}' was not found — pick an available model",
            ),
            provider_metadata=metadata,
        )

    # Unhandled APIStatusError (e.g. 409 Conflict, 422 Unprocessable Entity,
    # 500 Internal Server Error): split 4xx (non-retryable client error) from
    # 5xx (retryable server error). After the upfront guard and the
    # APIConnectionError branch, sdk_exc is necessarily an APIStatusError here.
    status_code = sdk_exc.status_code
    if 400 <= status_code < 500:
        msg = f"Anthropic client error (HTTP {status_code}) for model '{model_desc}': {sdk_exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.CONFIGURATION,
            user_action=UserAction(
                kind=UserActionKind.CHANGE_INPUT,
                detail="Anthropic rejected the request — review the prompt, parameters, and model configuration",
            ),
            provider_metadata=metadata,
        )
    msg = f"Anthropic API error (HTTP {status_code}) for model '{model_desc}': {sdk_exc}"
    return LLMCompletionError(
        msg,
        error_category=InferenceErrorCategory.TRANSIENT,
        user_action=UserAction(
            kind=UserActionKind.WAIT_AND_RETRY,
            detail="Anthropic returned an error — the system will retry automatically",
        ),
        provider_metadata=metadata,
    )
