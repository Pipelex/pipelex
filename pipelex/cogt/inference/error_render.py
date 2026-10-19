"""Provider-blind rendering of a classified inference error into a CogtError.

``render_inference_error`` is the single shared Render step of the
Extract / Classify / Render pipeline: it turns a ``ProviderErrorMetadata`` plus
a ``ClassificationResult`` into the appropriate ``CogtError`` subclass for the
worker's error family, with a human-readable message and a structured
``UserAction``.
"""

import math

from mthds.protocol.problem.registry import CoreCode, ModelUnavailableReason

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
from pipelex.cogt.inference.error_classify import ClassificationResult, InferenceErrorFamily
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode

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


# The kind of model each family's worker calls, which `model.unavailable` names.
_FAMILY_MODEL_TYPES: dict[InferenceErrorFamily, ModelType] = {
    InferenceErrorFamily.LLM: ModelType.LLM,
    InferenceErrorFamily.IMG_GEN: ModelType.IMG_GEN,
    InferenceErrorFamily.EXTRACT: ModelType.TEXT_EXTRACTOR,
    InferenceErrorFamily.SEARCH: ModelType.SEARCH,
    InferenceErrorFamily.JUDGMENT: ModelType.JUDGMENT,
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


def _render_context_exceeded_detail(*, family: InferenceErrorFamily) -> str:
    """Produce the advice for inputs over what the model can read, worded for what the family's model reads.

    The code, ``model.context_exceeded``, says the inputs exceed what the model can read, whatever the model. A language
    model's window holds the output a request reserves with ``max_tokens`` as well as the prompt, and its providers
    refuse both overflows alike, Anthropic's "input length and `max_tokens` exceed context limit" and OpenAI's
    "maximum context length" counting the completion beside the messages, so its advice names both. The
    ``max_tokens`` may be the deck's default rather than one the pipe set, and a pipe's own setting overrides it. An
    image model reads a prompt and its input images, and an extraction model a document, neither of which has a
    ``max_tokens`` to lower.
    """
    match family:
        case InferenceErrorFamily.LLM:
            return (
                "The prompt plus the output requested with max_tokens exceed the model's context window — shorten the input "
                "or lower max_tokens, or choose a model with a larger context window."
            )
        case InferenceErrorFamily.IMG_GEN:
            return "The prompt or its input images exceed what the image model can read — shorten the prompt or send fewer images."
        case InferenceErrorFamily.EXTRACT:
            return "The document exceeds what the extraction model can read — send a shorter document, or split it."
        case InferenceErrorFamily.SEARCH:
            return "The query built from the inputs exceeds what the search model can read — shorten the inputs."
        case InferenceErrorFamily.JUDGMENT:
            return "The material to judge exceeds what the judgment model can read — shorten it."


def _render_detail(metadata: SDKErrorEnvelope, *, classification: ClassificationResult, family: InferenceErrorFamily, model_handle: str) -> str:
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
    if classification.category.is_outcome_unknown:
        # A call that is not idempotent may have run: the kind's "run it again" would duplicate a billed result.
        return "The provider failed after the request was sent, so it may have produced and billed a result — check for one before running it again."
    match classification.user_action_kind:
        case UserActionKind.WAIT_AND_RETRY:
            # The advice is read on a failed run's report, once every automatic retry is spent, so
            # it says what the reader can do next and never promises another attempt by the system.
            # "At least" is a lower bound, so the provider's delay is rounded up, never down.
            if metadata.retry_after_seconds is not None:
                wait_seconds = math.ceil(metadata.retry_after_seconds)
                if wait_seconds > 0:
                    return f"Transient provider error — wait at least {wait_seconds}s, then run it again."
            return "Transient provider error — wait a moment, then run it again."
        case UserActionKind.CHECK_BILLING:
            return "Your account quota or credits are exhausted — check your billing dashboard."
        case UserActionKind.CHECK_CREDENTIALS:
            return "The provider rejected the credentials — check that the API key is valid and correctly configured."
        case UserActionKind.CHANGE_INPUT:
            # Worded from the code the classification picked, not from the metadata's wording, so a 5xx, or a parse
            # failure quoting the model's own text, never reads as the context window
            match classification.error_code:
                case CoreCode.MODEL_CONTEXT_EXCEEDED:
                    return _render_context_exceeded_detail(family=family)
                case CoreCode() | PipelexErrorCode():
                    pass
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
        ``UserAction``, and ``provider_metadata``, with the classification's code chosen.
    """
    message = _format_message(metadata, model_desc=model_desc)
    user_action = UserAction(
        kind=classification.user_action_kind,
        detail=_render_detail(metadata, classification=classification, family=family, model_handle=model_handle),
    )
    if classification.is_model_not_found:
        not_found_class = _NOT_FOUND_CLASSES[family]
        return not_found_class(
            message=message,
            model_handle=model_handle,
            error_category=classification.category,
            user_action=user_action,
            provider_metadata=metadata,
        ).with_params(model=model_handle, model_type=_FAMILY_MODEL_TYPES[family], reason=ModelUnavailableReason.UNKNOWN_AT_PROVIDER)
    # The not-found classes report ``model.unavailable`` alone, which the classification guarantees. A failure
    # class declares every classified code, and its code is chosen here rather than inherited, since the
    # provider's exception it is raised from carries none.
    failure_class = _FAILURE_CLASSES[family]
    failure = failure_class(
        message,
        error_category=classification.category,
        user_action=user_action,
        provider_metadata=metadata,
    ).with_error_code(classification.error_code)
    if classification.is_model_not_allowed:
        # The provider serves the model but does not allow it for this caller.
        failure.with_params(model=model_handle, model_type=_FAMILY_MODEL_TYPES[family], reason=ModelUnavailableReason.NOT_ALLOWED)
    return failure
