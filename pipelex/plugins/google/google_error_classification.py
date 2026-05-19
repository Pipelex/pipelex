"""Google GenAI SDK error classification for the LLM worker.

Single entry point ``classify_google_sdk_error`` returning a categorized error
(or ``None`` for an unrecognized exception type) so the caller controls raising
and ``raise ... from`` chaining.
"""

import httpx
from google.genai import errors as genai_errors

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError, LLMModelNotFoundError
from pipelex.cogt.inference.error_classification import (
    UserAction,
    UserActionKind,
    extract_google_metadata,
    is_content_policy_violation,
    is_quota_exhaustion_google,
)
from pipelex.urls import URLs


def _classify_google_client_error(
    exc: genai_errors.ClientError,
    model_desc: str,
    model_id: str,
    model_handle: str,
) -> LLMCompletionError | LLMModelNotFoundError:
    """Classify a Google GenAI ClientError into a categorized error.

    The returned error carries a structured ``provider_metadata`` and a
    semantic ``UserActionKind`` so downstream consumers (retry, CLI,
    telemetry) get uniform shape across providers. A 404 yields the
    ``LLMModelNotFoundError`` specialization.
    """
    error_message = str(exc)
    status_code = exc.code
    metadata = extract_google_metadata(exc)

    if status_code == 404:
        msg = f"Google model '{model_desc}' not found: {exc}"
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

    if status_code in {401, 403}:
        msg = f"Google API permission denied for model '{model_desc}': {exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.CONFIGURATION,
            user_action=UserAction(
                kind=UserActionKind.CHECK_CREDENTIALS,
                detail="Google rejected the API credentials — check your project, API key, and IAM permissions",
            ),
            provider_metadata=metadata,
        )

    if status_code == 429:
        if is_quota_exhaustion_google(error_message):
            msg = f"Google quota exhausted for model '{model_desc}': {exc}"
            return LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CAPACITY,
                user_action=UserAction(
                    kind=UserActionKind.CHECK_BILLING,
                    detail=f"Your Google Cloud account has exceeded its quota — check billing at {URLs.google_billing}",
                ),
                provider_metadata=metadata,
            )
        msg = f"Google rate limit exceeded for model '{model_desc}': {exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.TRANSIENT,
            user_action=UserAction(
                kind=UserActionKind.WAIT_AND_RETRY,
                detail="Rate limited by Google — the system will retry automatically",
            ),
            provider_metadata=metadata,
        )

    if status_code == 400:
        if is_content_policy_violation(error_message):
            msg = f"Content rejected by safety filters for model '{model_desc}': {exc}"
            return LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="Content was rejected by safety filters — revise the prompt",
                ),
                provider_metadata=metadata,
            )
        msg = f"Google bad request error for model '{model_desc}': {exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.CONTENT,
            user_action=UserAction(
                kind=UserActionKind.CHANGE_INPUT,
                detail="Google rejected the request — review the prompt and parameters",
            ),
            provider_metadata=metadata,
        )

    # Fallback for other 4xx errors: a ClientError is always 4xx, so it is a
    # non-retryable client-side problem — not a transient one.
    msg = f"Google API client error for model '{model_desc}': {exc}"
    return LLMCompletionError(
        msg,
        error_category=InferenceErrorCategory.CONFIGURATION,
        user_action=UserAction(
            kind=UserActionKind.CHANGE_INPUT,
            detail="Google rejected the request — review the prompt, parameters, and model configuration",
        ),
        provider_metadata=metadata,
    )


def classify_google_sdk_error(
    sdk_exc: BaseException,
    model_desc: str,
    model_id: str,
    model_handle: str,
) -> LLMCompletionError | LLMModelNotFoundError | None:
    """Build a categorized error from a Google GenAI SDK exception.

    Returns ``None`` when ``sdk_exc`` is not a ``ServerError`` / ``ClientError``
    / ``httpx.TransportError``, so callers can apply their own fallback (e.g. an
    instructor exception whose underlying cause could not be recovered). A
    ``ClientError`` 404 yields the ``LLMModelNotFoundError`` specialization.

    ``ServerError`` is handled directly here — it doesn't need the 4xx
    discriminator in ``_classify_google_client_error``. ``httpx.TransportError``
    is also handled: the Google GenAI SDK does not wrap connection / timeout
    failures into ``ServerError`` / ``ClientError`` — it lets the raw ``httpx``
    exception propagate — so it must be categorized here too.

    Args:
        sdk_exc: The exception to classify.
        model_desc: Human-readable model description for error messages.
        model_id: The provider-side model id.
        model_handle: The pipelex model handle, carried on ``LLMModelNotFoundError``.
    """
    if isinstance(sdk_exc, genai_errors.ServerError):
        msg = f"Google API server error for model '{model_desc}': {sdk_exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.TRANSIENT,
            user_action=UserAction(
                kind=UserActionKind.WAIT_AND_RETRY,
                detail="Google API server error — the system will retry automatically",
            ),
            provider_metadata=extract_google_metadata(sdk_exc),
        )
    if isinstance(sdk_exc, genai_errors.ClientError):
        return _classify_google_client_error(exc=sdk_exc, model_desc=model_desc, model_id=model_id, model_handle=model_handle)
    if isinstance(sdk_exc, httpx.TransportError):
        msg = f"Google API transport error for model '{model_desc}': {sdk_exc}"
        return LLMCompletionError(
            msg,
            error_category=InferenceErrorCategory.TRANSIENT,
            user_action=UserAction(
                kind=UserActionKind.WAIT_AND_RETRY,
                detail="Could not reach Google — the system will retry automatically",
            ),
            provider_metadata=None,
        )
    return None
