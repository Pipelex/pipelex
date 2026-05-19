"""Mistral SDK error classification for the LLM worker.

Single entry point ``classify_mistral_sdk_error`` so the type→category mapping
lives in one place instead of being repeated across ``_gen_text`` / ``_gen_object``
and the ``InstructorRetryException`` handler.
"""

import httpx
from mistralai import MistralError

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError, LLMModelNotFoundError
from pipelex.cogt.inference.error_classification import (
    UserAction,
    UserActionKind,
    extract_mistral_metadata,
    is_content_policy_violation,
    is_quota_exhaustion_mistral,
)
from pipelex.urls import URLs


def classify_mistral_sdk_error(
    sdk_exc: BaseException,
    model_desc: str,
    model_id: str,
    model_handle: str,
) -> LLMCompletionError | LLMModelNotFoundError | None:
    """Build a categorized error from a Mistral SDK exception.

    Returns ``None`` when ``sdk_exc`` is neither a ``MistralError`` nor a raw
    ``httpx.TransportError``, so callers can apply their own fallback (e.g. an
    instructor exception whose underlying cause could not be recovered). A 404
    ``MistralError`` yields the ``LLMModelNotFoundError`` specialization.

    The Mistral SDK does not wrap connection / timeout failures into
    ``MistralError`` — it lets the raw ``httpx`` exception propagate — so a
    transport failure is categorized here too rather than keyed off
    ``MistralError.status_code``.

    Args:
        sdk_exc: The exception to classify.
        model_desc: Human-readable model description for error messages.
        model_id: The provider-side model id.
        model_handle: The pipelex model handle, carried on ``LLMModelNotFoundError``.
    """
    if isinstance(sdk_exc, httpx.TransportError):
        msg = f"Mistral API transport error for model '{model_desc}': {sdk_exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.TRANSIENT,
            user_action=UserAction(
                kind=UserActionKind.WAIT_AND_RETRY,
                detail="Could not reach Mistral — the system will retry automatically",
            ),
            provider_metadata=None,
        )

    if not isinstance(sdk_exc, MistralError):
        return None

    error_message = str(sdk_exc)
    status_code = sdk_exc.status_code
    metadata = extract_mistral_metadata(sdk_exc)

    if is_quota_exhaustion_mistral(error_message, status_code):
        msg = f"Mistral quota exhausted for model '{model_desc}': {sdk_exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.CAPACITY,
            user_action=UserAction(
                kind=UserActionKind.CHECK_BILLING,
                detail=f"Your Mistral account has exceeded its quota — check billing at {URLs.mistral_billing}",
            ),
            provider_metadata=metadata,
        )

    if status_code in {401, 403}:
        msg = f"Mistral authentication error for model '{model_desc}': {sdk_exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.CONFIGURATION,
            user_action=UserAction(
                kind=UserActionKind.CHECK_CREDENTIALS,
                detail="Mistral rejected the API key — check your credentials",
            ),
            provider_metadata=metadata,
        )

    if status_code == 404:
        msg = f"Mistral model '{model_desc}' not found: {sdk_exc}"
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

    if status_code == 429:
        msg = f"Mistral rate limit exceeded for model '{model_desc}': {sdk_exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.TRANSIENT,
            user_action=UserAction(
                kind=UserActionKind.WAIT_AND_RETRY,
                detail="Rate limited by Mistral — the system will retry automatically",
            ),
            provider_metadata=metadata,
        )

    if status_code == 400:
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
        msg = f"Mistral bad request error for model '{model_desc}': {sdk_exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.CONTENT,
            user_action=UserAction(
                kind=UserActionKind.CHANGE_INPUT,
                detail="Mistral rejected the request — review the prompt and parameters",
            ),
            provider_metadata=metadata,
        )

    if status_code >= 500:
        msg = f"Mistral server error for model '{model_desc}': {sdk_exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.TRANSIENT,
            user_action=UserAction(
                kind=UserActionKind.WAIT_AND_RETRY,
                detail="Mistral server error — the system will retry automatically",
            ),
            provider_metadata=metadata,
        )

    if 400 <= status_code < 500:
        msg = f"Mistral client error for model '{model_desc}': {sdk_exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.CONFIGURATION,
            user_action=UserAction(
                kind=UserActionKind.CHANGE_INPUT,
                detail="Mistral rejected the request — review the prompt, parameters, and model configuration",
            ),
            provider_metadata=metadata,
        )

    msg = f"Mistral API error for model '{model_desc}': {sdk_exc}"
    return LLMCompletionError(
        msg,
        error_category=InferenceErrorCategory.TRANSIENT,
        user_action=UserAction(
            kind=UserActionKind.WAIT_AND_RETRY,
            detail="Mistral API returned an unexpected error — the system will retry automatically",
        ),
        provider_metadata=metadata,
    )
