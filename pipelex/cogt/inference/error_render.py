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


# Generic failure error class per family — used when the error is not a missing model.
_FAILURE_CLASSES: dict[InferenceErrorFamily, type[CogtError]] = {
    InferenceErrorFamily.LLM: LLMCompletionError,
    InferenceErrorFamily.IMG_GEN: ImgGenGenerationError,
    InferenceErrorFamily.EXTRACT: ExtractJobFailureError,
    InferenceErrorFamily.SEARCH: SearchJobFailureError,
}

# Model-not-found error class per family — used when ``is_model_not_found`` is set.
_NOT_FOUND_CLASSES: dict[InferenceErrorFamily, type[ModelNotFoundError]] = {
    InferenceErrorFamily.LLM: LLMModelNotFoundError,
    InferenceErrorFamily.IMG_GEN: ImgGenModelNotFoundError,
    InferenceErrorFamily.EXTRACT: ExtractModelNotFoundError,
    InferenceErrorFamily.SEARCH: SearchModelNotFoundError,
}


def _format_message(metadata: SDKErrorEnvelope, *, model_desc: str) -> str:
    """Compose the human-readable error message from the provider, model, and SDK text."""
    status_part = f" (HTTP {metadata.status_code})" if metadata.status_code is not None else ""
    return f"{metadata.provider} inference failed for model '{model_desc}'{status_part}: {metadata.message}"


def _render_detail(metadata: SDKErrorEnvelope, *, classification: ClassificationResult) -> str:
    """Produce the free-form user-facing advice text for the classified error."""
    match classification.user_action_kind:
        case UserActionKind.WAIT_AND_RETRY:
            if metadata.retry_after_seconds is not None:
                return f"Transient provider error — the system will retry automatically after {metadata.retry_after_seconds:.0f}s."
            return "Transient provider error — the system will retry automatically."
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
        model_handle: The pipelex model handle, carried on ``*ModelNotFoundError``.

    Returns:
        A ``CogtError`` subclass instance carrying the category, structured
        ``UserAction``, and ``provider_metadata``.
    """
    message = _format_message(metadata, model_desc=model_desc)
    user_action = UserAction(
        kind=classification.user_action_kind,
        detail=_render_detail(metadata, classification=classification),
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
