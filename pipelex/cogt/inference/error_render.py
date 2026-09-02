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
from pipelex.cogt.inference.error_classification import (
    GatewayRequestLimit,
    GatewayRoutingRefusal,
    GatewayUnresolvedReference,
    SDKErrorEnvelope,
    UserAction,
    UserActionKind,
)
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


def _render_gateway_limit_detail(*, limit: GatewayRequestLimit) -> str:
    """Produce the advice for a request-shape refusal the inference gateway raised itself.

    Deliberately says nothing about a number. The caps are the deployment's, they
    differ between deployments, and the gateway already names its own figures in
    the message this detail sits beside — repeating a compiled-in guess here is how
    advice starts contradicting the refusal it explains.

    **This is where a per-plan message belongs** once the hosted product's tier
    limits are wired through: the gateway knows nothing of users, organisations or
    plans, so "your plan allows files up to N MB" can only be said from here.
    """
    match limit:
        case GatewayRequestLimit.BODY_TOO_LARGE:
            return "The request was too large for the inference gateway — send less in one call, or use smaller inputs."
        case GatewayRequestLimit.OBJECT_TOO_LARGE:
            return "A file the request refers to is over the inference gateway's per-file size limit — use a smaller file."
        case GatewayRequestLimit.BODY_TOO_DEEP:
            return "The request nests too deeply for the inference gateway — flatten the inputs or the output structure."
        case GatewayRequestLimit.BODY_LENGTH_REQUIRED:
            return (
                "The inference gateway could not read the request's declared size and refused it: it requires a "
                "Content-Length and does not accept a chunked body. Nothing about the inputs causes this — contact support."
            )


def _render_gateway_unresolved_reference_detail(*, reference: GatewayUnresolvedReference) -> str:
    """Produce the advice for a reference the inference gateway could not resolve.

    Names no key, host, status or media type, for the same reason
    ``_render_gateway_limit_detail`` names no number: the gateway's own refusal
    message sits beside this detail and already states the specifics. What this
    text adds is what the caller should *do*, which the message does not say.
    """
    match reference:
        case GatewayUnresolvedReference.REFERENCE_UNRESOLVED:
            return (
                "A file reference in the request could not be resolved by the inference gateway — "
                "the error message names the cause; fix the reference it names."
            )
        case GatewayUnresolvedReference.STORAGE_REFERENCE_INVALID:
            return "The pipelex-storage:// reference in the request is malformed — check it against the key the upload returned."
        case GatewayUnresolvedReference.STORAGE_OBJECT_UNREADABLE:
            return (
                "The referenced storage object does not exist or cannot be read — check that the reference points at a file "
                "uploaded to this deployment."
            )
        case GatewayUnresolvedReference.STORAGE_NOT_SERVED:
            return (
                "This inference gateway does not serve pipelex-storage:// references at all — no storage is configured for it. "
                "Nothing about the inputs causes this — contact support."
            )
        case GatewayUnresolvedReference.DOCUMENT_URL_REFUSED:
            return (
                "The inference gateway refused the document URL — send a plain public https:// URL, a data: URL, or a "
                "pipelex-storage:// reference, and give the final address rather than one that redirects."
            )
        case GatewayUnresolvedReference.DOCUMENT_HOST_REFUSED:
            return (
                "The inference gateway does not fetch documents from that host, as a matter of security policy: private and "
                "internal addresses are never fetched. Host the document at a publicly reachable address, or upload it to "
                "Pipelex storage and reference it from there."
            )
        case GatewayUnresolvedReference.DOCUMENT_UNREACHABLE:
            return (
                "The document could not be fetched from its URL — check that it is live and publicly reachable, and try again "
                "if its host was temporarily down."
            )
        case GatewayUnresolvedReference.DOCUMENT_CONTENT_UNUSABLE:
            return (
                "The document was fetched but cannot be used — the error message says whether it was served empty, in a media "
                "type the pipeline does not accept, or as a data: URL that could not be decoded."
            )


def _render_gateway_routing_refusal_detail(*, refusal: GatewayRoutingRefusal) -> str:
    """Produce the advice for a request the inference gateway refused to route.

    Names no model, integration, protocol or capability, for the same reason
    ``_render_gateway_limit_detail`` names no number: the gateway's own refusal
    message sits beside this detail and already states every specific. What this
    text adds is what the caller — or whoever operates the deployment — should
    *do*, which the message does not say.

    Two of the four say "the model deck" out loud. The runtime picks the protocol
    and the route from its own deck, so those refusals usually mean the deck and
    the gateway disagree about a model rather than that the caller chose badly, and
    advice that only said "pick another model" would send an operator hunting for a
    model problem that is a configuration problem.
    """
    match refusal:
        case GatewayRoutingRefusal.UNKNOWN_MODEL:
            return (
                "The inference gateway does not serve that model — pick a model this deployment serves. "
                "If your model deck lists it, the deck and the gateway disagree about what is available."
            )
        case GatewayRoutingRefusal.DISABLED_INTEGRATION:
            return (
                "The model is served by an integration this inference gateway has not enabled — its credentials are unset. "
                "Nothing about the request causes this, and none of your own credentials are at fault: the error message "
                "names the integration and the variables whoever operates the gateway has to set. Contact support."
            )
        case GatewayRoutingRefusal.WRONG_PROTOCOL:
            return (
                "The inference gateway serves that model, but not over the protocol the request used for it — your model "
                "deck names a different backend for it than the gateway routes it to. Correct the deck, or pick another model."
            )
        case GatewayRoutingRefusal.UNSERVED_CAPABILITY:
            return (
                "The model's integration does not serve that capability on the inference gateway — the error message names "
                "the provider and what was asked of it. Pick a model whose provider serves it, or correct the model deck."
            )


def _render_detail(metadata: SDKErrorEnvelope, *, classification: ClassificationResult) -> str:
    """Produce the free-form user-facing advice text for the classified error."""
    if classification.gateway_request_limit is not None:
        # Branches ahead of the action kind rather than inside it: the limit names
        # the remedy more precisely than the kind does, and two of the four limits
        # would otherwise land on advice that is simply wrong for them.
        return _render_gateway_limit_detail(limit=classification.gateway_request_limit)
    if classification.gateway_unresolved_reference is not None:
        # Same reason, one indirection further out: every member here would
        # otherwise render "review the prompt, parameters, and inputs" for a
        # reference the caller has to repair, and one of them for a security
        # refusal that no reshaping of the inputs can get around.
        return _render_gateway_unresolved_reference_detail(reference=classification.gateway_unresolved_reference)
    if classification.gateway_routing_refusal is not None:
        # Same reason a third time, and here the action kind is wrong for every
        # member rather than for some: ``CHANGE_MODEL`` renders "the requested
        # model was not found", which is true of one of the four and false of the
        # three whose model exists and is served, and ``CONTACT_SUPPORT`` renders
        # "the error could not be classified" for a refusal that named itself
        # precisely.
        return _render_gateway_routing_refusal_detail(refusal=classification.gateway_routing_refusal)
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
