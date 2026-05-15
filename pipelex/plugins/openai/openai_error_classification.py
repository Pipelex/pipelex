"""Shared OpenAI SDK error classification for LLM workers.

The Completions and Responses workers raise identical categorized errors from
OpenAI SDK exceptions; this module holds the single implementation so the two
cannot drift.
"""

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError, LLMModelNotFoundError
from pipelex.cogt.inference.error_classification import (
    UserAction,
    UserActionKind,
    extract_openai_metadata,
    is_content_policy_violation,
    is_quota_exhaustion_openai,
)
from pipelex.urls import URLs


def classify_openai_sdk_error(
    sdk_exc: BaseException,
    model_desc: str,
    model_id: str,
    model_handle: str,
) -> LLMCompletionError | LLMModelNotFoundError | None:
    """Build a categorized error from an OpenAI SDK exception.

    Returns ``None`` when ``sdk_exc`` is not an OpenAI HTTP-status or connection
    error, so callers can apply their own fallback (e.g. an instructor exception
    whose underlying cause could not be recovered). ``NotFoundError`` yields the
    ``LLMModelNotFoundError`` specialization so callers can swap models.

    Args:
        sdk_exc: The exception to classify.
        model_desc: Human-readable model description for error messages.
        model_id: The provider-side model id.
        model_handle: The pipelex model handle, carried on ``LLMModelNotFoundError``.
    """
    if not isinstance(sdk_exc, (APIStatusError, APIConnectionError)):
        return None
    metadata = extract_openai_metadata(sdk_exc)

    if isinstance(sdk_exc, RateLimitError):
        error_message = str(sdk_exc)
        if is_quota_exhaustion_openai(error_message):
            msg = f"OpenAI quota exhausted for model '{model_desc}': {sdk_exc}"
            return LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CAPACITY,
                user_action=UserAction(
                    kind=UserActionKind.CHECK_BILLING,
                    detail=f"Your OpenAI account has exceeded its quota — check billing at {URLs.openai_billing}",
                ),
                provider_metadata=metadata,
            )
        msg = f"OpenAI rate limit exceeded for model '{model_desc}': {sdk_exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.TRANSIENT,
            user_action=UserAction(
                kind=UserActionKind.WAIT_AND_RETRY,
                detail="Rate limited by OpenAI — the system will retry automatically",
            ),
            provider_metadata=metadata,
        )

    if isinstance(sdk_exc, APITimeoutError):
        msg = f"OpenAI API request timed out for model '{model_desc}': {sdk_exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.TRANSIENT,
            user_action=UserAction(
                kind=UserActionKind.WAIT_AND_RETRY,
                detail="OpenAI API request timed out — the system will retry automatically",
            ),
            provider_metadata=metadata,
        )

    if isinstance(sdk_exc, APIConnectionError):
        msg = f"OpenAI API connection error: {sdk_exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.TRANSIENT,
            user_action=UserAction(
                kind=UserActionKind.WAIT_AND_RETRY,
                detail="Could not reach OpenAI — the system will retry automatically",
            ),
            provider_metadata=metadata,
        )

    if isinstance(sdk_exc, InternalServerError):
        msg = f"OpenAI API server error for model '{model_desc}': {sdk_exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.TRANSIENT,
            user_action=UserAction(
                kind=UserActionKind.WAIT_AND_RETRY,
                detail="OpenAI server error — the system will retry automatically",
            ),
            provider_metadata=metadata,
        )

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
        msg = f"OpenAI bad request error with model '{model_desc}': {sdk_exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.CONTENT,
            user_action=UserAction(
                kind=UserActionKind.CHANGE_INPUT,
                detail="OpenAI rejected the request — review the prompt and parameters",
            ),
            provider_metadata=metadata,
        )

    if isinstance(sdk_exc, PermissionDeniedError):
        msg = f"OpenAI permission denied: {sdk_exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.CONFIGURATION,
            user_action=UserAction(
                kind=UserActionKind.CHECK_CREDENTIALS,
                detail="OpenAI denied permission — check your API key permissions",
            ),
            provider_metadata=metadata,
        )

    if isinstance(sdk_exc, AuthenticationError):
        msg = f"OpenAI authentication error: {sdk_exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.CONFIGURATION,
            user_action=UserAction(
                kind=UserActionKind.CHECK_CREDENTIALS,
                detail="OpenAI rejected the API key — check your credentials",
            ),
            provider_metadata=metadata,
        )

    # Unhandled APIStatusError (e.g. 409 Conflict, 422 Unprocessable Entity):
    # split 4xx (non-retryable client error) from 5xx (retryable server error).
    status_code = sdk_exc.status_code
    if 400 <= status_code < 500:
        msg = f"OpenAI client error (HTTP {status_code}) for model '{model_desc}': {sdk_exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.CONFIGURATION,
            user_action=UserAction(
                kind=UserActionKind.CHANGE_INPUT,
                detail="OpenAI rejected the request — review the prompt, parameters, and model configuration",
            ),
            provider_metadata=metadata,
        )
    msg = f"OpenAI API error (HTTP {status_code}) for model '{model_desc}': {sdk_exc}"
    return LLMCompletionError(
        msg,
        error_category=InferenceErrorCategory.TRANSIENT,
        user_action=UserAction(
            kind=UserActionKind.WAIT_AND_RETRY,
            detail="OpenAI returned an error — the system will retry automatically",
        ),
        provider_metadata=metadata,
    )
