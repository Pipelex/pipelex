"""Provider-blind rendering of a classified inference error into a CogtError.

``render_inference_error`` is the single shared Render step of the
Extract / Classify / Render pipeline: it turns a ``ProviderErrorMetadata`` plus
a ``ClassificationResult`` into the appropriate ``CogtError`` subclass for the
worker's error family, with a human-readable message and a structured
``UserAction``.
"""

from enum import StrEnum

from pipelex.cogt.exceptions import (
    CogtError,
    ExtractJobFailureError,
    ExtractModelNotFoundError,
    ImgGenGenerationError,
    ImgGenModelNotFoundError,
    JudgmentJobFailureError,
    JudgmentModelNotFoundError,
    LLMCompletionError,
    LLMModelNotFoundError,
    ModelNotFoundError,
    SearchJobFailureError,
    SearchModelNotFoundError,
)
from pipelex.cogt.inference.error_classification import SDKErrorEnvelope, UserAction, UserActionKind
from pipelex.cogt.inference.error_classify import ClassificationResult


class InferenceErrorFamily(StrEnum):
    """The worker family raising an inference error — selects the exception class."""

    LLM = "llm"
    IMG_GEN = "img_gen"
    EXTRACT = "extract"
    SEARCH = "search"
    JUDGMENT = "judgment"


# Generic failure error class per family — used when the error is not a missing model.
_FAILURE_CLASSES: dict[InferenceErrorFamily, type[CogtError]] = {
    InferenceErrorFamily.LLM: LLMCompletionError,
    InferenceErrorFamily.IMG_GEN: ImgGenGenerationError,
    InferenceErrorFamily.EXTRACT: ExtractJobFailureError,
    InferenceErrorFamily.SEARCH: SearchJobFailureError,
    InferenceErrorFamily.JUDGMENT: JudgmentJobFailureError,
}

# Model-not-found error class per family — used when ``is_model_not_found`` is set.
_NOT_FOUND_CLASSES: dict[InferenceErrorFamily, type[ModelNotFoundError]] = {
    InferenceErrorFamily.LLM: LLMModelNotFoundError,
    InferenceErrorFamily.IMG_GEN: ImgGenModelNotFoundError,
    InferenceErrorFamily.EXTRACT: ExtractModelNotFoundError,
    InferenceErrorFamily.SEARCH: SearchModelNotFoundError,
    InferenceErrorFamily.JUDGMENT: JudgmentModelNotFoundError,
}


def _format_message(metadata: SDKErrorEnvelope, *, model_desc: str) -> str:
    """Compose the human-readable error message from the provider, model, and SDK text."""
    status_part = f" (HTTP {metadata.status_code})" if metadata.status_code is not None else ""
    return f"{metadata.provider} inference failed for model '{model_desc}'{status_part}: {metadata.message}"


def _render_model_not_allowed_detail(*, model_handle: str) -> str:
    """Produce the advice for a model an integration serves but does not allow for this caller.

    The refusal's own message names only the backend's wire id, which the method's author never
    wrote, so the advice names ``model_handle``, the handle the model deck resolved the pipe's model
    to. Both halves are conditional because the Render step cannot tell the cases apart: the handle
    may be one the pipe named or the deck's default, and leaving the model unset only helps in the
    first case; and a deck listing a model the allow-list refuses is the gateway operator's to settle
    on a hosted gateway, and the caller's on a Portkey workspace of their own.
    """
    return (
        f"The inference gateway does not allow the model '{model_handle}' for this account — pick another model for the "
        "pipe; if the pipe named this one, leaving its model unset uses the default instead. If your model deck lists "
        "it as available, the deck and the gateway's allow-list disagree: on a hosted gateway, contact support; on "
        "a Portkey workspace of your own, allow the model in the integration that serves it."
    )


def _render_detail(metadata: SDKErrorEnvelope, *, classification: ClassificationResult, model_handle: str) -> str:
    """Produce the free-form user-facing advice text for the classified error."""
    if classification.service_error_code is not None:
        # Branches ahead of the action kind rather than inside it: the service's own code names the
        # remedy more precisely than the kind does, and the kind's generic advice is often simply
        # wrong for it — "review the prompt" for a reference to fix, "the model was not found" for a
        # model that exists but cannot do what was asked.
        return classification.service_error_code.detail
    if classification.is_model_not_allowed:
        # Same reason: ``CHANGE_MODEL`` renders "the requested model was not found", which is false
        # for a model that exists and is served, only not for this caller.
        return _render_model_not_allowed_detail(model_handle=model_handle)
    match classification.user_action_kind:
        case UserActionKind.WAIT_AND_RETRY:
            # The advice is read on a failed run's report, once every automatic retry is spent, so
            # it says what the reader can do next and never promises another attempt by the system.
            if metadata.retry_after_seconds is not None:
                return f"Transient provider error — wait at least {metadata.retry_after_seconds:.0f}s, then run it again."
            return "Transient provider error — wait a moment, then run it again."
        case UserActionKind.CHECK_BILLING:
            return "Your account quota or credits are exhausted — check your billing dashboard."
        case UserActionKind.CHECK_CREDENTIALS:
            return "The provider rejected the credentials — check that the API key is valid and correctly configured."
        case UserActionKind.CHANGE_INPUT:
            if metadata.is_content_policy_violation:
                return "Content was rejected by the provider's safety filters — revise the prompt."
            return "The provider rejected the request — review the prompt, parameters, and inputs."
        case UserActionKind.CHANGE_MODEL:
            return "The requested model was not found — pick an available model."
        case UserActionKind.CONTACT_SUPPORT | UserActionKind.UNKNOWN:
            return "The error could not be classified — contact support if the problem persists."


def render_inference_error(
    metadata: SDKErrorEnvelope,
    *,
    classification: ClassificationResult,
    family: InferenceErrorFamily,
    model_desc: str,
    model_handle: str,
) -> CogtError:
    """Render a classified inference error into the appropriate ``CogtError`` subclass.

    Args:
        metadata: The structured envelope from the Extract step.
        classification: The result of the Classify step.
        family: The worker family, selecting the concrete exception class.
        model_desc: Human-readable model description for the error message.
        model_handle: The pipelex model handle, carried on ``*ModelNotFoundError`` and named by
            the advice of a routing refusal whose own message names only the backend's id.

    Returns:
        A ``CogtError`` subclass instance carrying the category, structured
        ``UserAction``, and ``provider_metadata``.
    """
    message = _format_message(metadata, model_desc=model_desc)
    user_action = UserAction(
        kind=classification.user_action_kind,
        detail=_render_detail(metadata, classification=classification, model_handle=model_handle),
    )
    if classification.is_model_not_found:
        not_found_class = _NOT_FOUND_CLASSES[family]
        return not_found_class(
            message=message,
            model_handle=model_handle,
            error_category=classification.category,
            user_action=user_action,
            provider_metadata=metadata,
        )
    failure_class = _FAILURE_CLASSES[family]
    return failure_class(
        message,
        error_category=classification.category,
        user_action=user_action,
        provider_metadata=metadata,
    )
