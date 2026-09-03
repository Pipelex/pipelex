"""Provider-blind classification of inference SDK errors.

``classify_inference_error`` is the single shared Classify step of the
Extract / Classify / Render pipeline. It is a pure function: it maps the
structured ``ProviderErrorMetadata`` produced by a provider's
``extract_*_metadata`` function to a ``ClassificationResult``, with no
provider-specific branching and no SDK imports.

Every provider-specific nuance has already been normalized into the metadata
by the Extract step (e.g. Google's ``code`` becomes ``status_code``;
quota-vs-rate-limit is decided by the ``is_quota_exhaustion`` property). The
HTTP status code drives classification; status-less errors dispatch on the
SDK exception type name.
"""

from pydantic import BaseModel

from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.cogt.inference.error_classification import (
    GatewayRequestLimit,
    GatewayRoutingRefusal,
    GatewayUnresolvedReference,
    SDKErrorEnvelope,
    UserActionKind,
)


class ClassificationResult(BaseModel):
    """Outcome of classifying an inference SDK error.

    ``is_model_not_found`` is a flag, not a category: the category stays
    ``CONFIGURATION`` for a missing model — only the rendered exception class
    differs (a ``*ModelNotFoundError`` rather than a generic failure error).
    """

    category: InferenceErrorCategory
    user_action_kind: UserActionKind
    is_model_not_found: bool = False
    # Which of the inference gateway's request-shape limits was hit, when the
    # refusal came from the gateway itself rather than from a provider. Like
    # ``is_model_not_found`` this is a flag rather than a category: it does not
    # change the retry decision, it lets the Render step say which limit was hit
    # instead of falling back to the generic "the provider rejected the request".
    gateway_request_limit: GatewayRequestLimit | None = None
    # Which of the gateway's unresolvable-reference refusals this is, when the
    # request named a file the gateway could not turn into bytes. A flag for the
    # same reason as the field above: the retry decision is unchanged, but the
    # Render step can say which reference failed and how, instead of telling a
    # caller with a mistyped storage key to revise their prompt.
    gateway_unresolved_reference: GatewayUnresolvedReference | None = None
    # Which of the gateway's routing refusals this is, when the gateway could not
    # decide which provider should serve the request at all. A flag for the same
    # reason as the two fields above: the retry decision is unchanged, but the
    # Render step can say that the *gateway* refused to route the model, instead
    # of telling a caller who named a model it does not serve to revise their
    # prompt — or, for the three whose model does exist, instead of the generic
    # "the requested model was not found".
    gateway_routing_refusal: GatewayRoutingRefusal | None = None


# Status-less SDK exception type names recognizable regardless of provider:
# the pydantic / instructor schema-validation failure and the uniquely-named
# Linkup typed exceptions (which carry no HTTP status). Network/transport
# failures are handled earlier via the metadata's ``is_network_error`` property.
_STATUSLESS_BY_TYPE_NAME: dict[str, tuple[InferenceErrorCategory, UserActionKind]] = {
    # pydantic / instructor schema-validation failure
    "ValidationError": (InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
    # Linkup typed SDK exceptions. ``LinkupTimeoutError`` and any
    # connection-shaped variants flow through ``is_network_error`` (the
    # ``_NETWORK_ERROR_TOKENS`` check matches "timeout"/"connect"), so they are
    # intentionally absent from this map.
    "LinkupAuthenticationError": (InferenceErrorCategory.CONFIGURATION, UserActionKind.CHECK_CREDENTIALS),
    "LinkupInsufficientCreditError": (InferenceErrorCategory.CAPACITY, UserActionKind.CHECK_BILLING),
    "LinkupTooManyRequestsError": (InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY),
    "LinkupInvalidRequestError": (InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
    "LinkupNoResultError": (InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
    "LinkupFetchResponseTooLargeError": (InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
    "LinkupFetchUrlIsFileError": (InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
    "LinkupFailedFetchError": (InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY),
    "LinkupUnknownError": (InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY),
    # FAL's typed credential failure — raised before any HTTP call when the API key is unset
    "MissingCredentialsError": (InferenceErrorCategory.CONFIGURATION, UserActionKind.CHECK_CREDENTIALS),
    # FAL's generic SDK error (base class) — caught last in the worker; HTTP/timeout variants
    # are peeled off earlier, so this branch represents the residual SDK failure.
    "FalClientError": (InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY),
}

# Builtin exception type names raised by the local file-based extractors
# (docling, pypdfium2). Interpreted only when the provider is a local file
# extractor — the same builtin type means something else from an SDK provider.
_LOCAL_EXTRACT_BY_TYPE_NAME: dict[str, tuple[InferenceErrorCategory, UserActionKind]] = {
    "FileNotFoundError": (InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
    "ValueError": (InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
    "RuntimeError": (InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
    "OSError": (InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY),
}


def _classify_statusless(metadata: SDKErrorEnvelope) -> ClassificationResult:
    """Classify an error that never reached an HTTP status (transport failure or local error)."""
    if metadata.is_network_error:
        return ClassificationResult(
            category=InferenceErrorCategory.TRANSIENT,
            user_action_kind=UserActionKind.WAIT_AND_RETRY,
        )
    # The provider-agnostic map (pydantic / Linkup) takes precedence; the local
    # file-extractor map is a fallback applied only for docling / pypdfium2,
    # where builtins like ``ValueError`` carry an extraction-specific meaning.
    # The two maps share no type names, so precedence is currently moot.
    type_name = metadata.sdk_exception_type
    mapped = _STATUSLESS_BY_TYPE_NAME.get(type_name)
    if mapped is None and metadata.provider.is_local_file_extractor:
        mapped = _LOCAL_EXTRACT_BY_TYPE_NAME.get(type_name)
    if mapped is not None:
        category, user_action_kind = mapped
        return ClassificationResult(category=category, user_action_kind=user_action_kind)
    return ClassificationResult(
        category=InferenceErrorCategory.UNKNOWN,
        user_action_kind=UserActionKind.CONTACT_SUPPORT,
    )


def _classify_gateway_request_limit(*, limit: GatewayRequestLimit) -> ClassificationResult:
    """Classify a request-shape refusal the inference gateway raised on its own.

    None of these is retryable and none is a provider failure: the gateway refused
    the request before a provider ever saw it, and sending the identical request
    again earns the identical refusal.
    """
    match limit:
        case GatewayRequestLimit.BODY_TOO_LARGE | GatewayRequestLimit.OBJECT_TOO_LARGE | GatewayRequestLimit.BODY_TOO_DEEP:
            # The caller sent more than the deployment serves — a smaller input is
            # the whole remedy, and it is theirs to make.
            return ClassificationResult(
                category=InferenceErrorCategory.CONTENT,
                user_action_kind=UserActionKind.CHANGE_INPUT,
                gateway_request_limit=limit,
            )
        case GatewayRequestLimit.BODY_LENGTH_REQUIRED:
            # Nothing about the *content* is wrong here: an HTTP client framed the
            # request in a way the gateway will not bound. No client the runtime
            # ships produces it, so reaching this means something in the transport
            # stack changed — which is an operator's problem, not the caller's.
            return ClassificationResult(
                category=InferenceErrorCategory.CONFIGURATION,
                user_action_kind=UserActionKind.CONTACT_SUPPORT,
                gateway_request_limit=limit,
            )


def _classify_gateway_unresolved_reference(*, reference: GatewayUnresolvedReference) -> ClassificationResult:
    """Classify an unresolvable-reference refusal the inference gateway raised on its own.

    None of these is retryable, for the same reason none of the request-shape
    limits is: the gateway refused before a provider saw the request, and the same
    reference resolves the same way the second time. That includes
    ``DOCUMENT_UNREACHABLE``, where the origin *could* have been transiently down —
    the gateway renders it a 400, a retry would re-run a whole inference call just
    to re-fetch a document, and the common case is a URL that is simply wrong.
    """
    match reference:
        case (
            GatewayUnresolvedReference.REFERENCE_UNRESOLVED
            | GatewayUnresolvedReference.STORAGE_REFERENCE_INVALID
            | GatewayUnresolvedReference.STORAGE_OBJECT_UNREADABLE
            | GatewayUnresolvedReference.DOCUMENT_URL_REFUSED
            | GatewayUnresolvedReference.DOCUMENT_HOST_REFUSED
            | GatewayUnresolvedReference.DOCUMENT_UNREACHABLE
            | GatewayUnresolvedReference.DOCUMENT_CONTENT_UNUSABLE
        ):
            # The reference is the caller's to fix — a different key, a different
            # URL, or the file uploaded where the gateway can reach it.
            # ``DOCUMENT_HOST_REFUSED`` belongs here too: the refusal is a security
            # policy rather than a fault, but the caller is still the one who can
            # act on it, and the Render step is where that distinction is stated.
            return ClassificationResult(
                category=InferenceErrorCategory.CONTENT,
                user_action_kind=UserActionKind.CHANGE_INPUT,
                gateway_unresolved_reference=reference,
            )
        case GatewayUnresolvedReference.STORAGE_NOT_SERVED:
            # This deployment serves no ``pipelex-storage://`` references at all,
            # because no bucket is configured for it. Nothing about the inputs
            # causes it and no input can avoid it — it is an operator's problem,
            # like ``BODY_LENGTH_REQUIRED``.
            return ClassificationResult(
                category=InferenceErrorCategory.CONFIGURATION,
                user_action_kind=UserActionKind.CONTACT_SUPPORT,
                gateway_unresolved_reference=reference,
            )


def _classify_gateway_routing_refusal(*, refusal: GatewayRoutingRefusal) -> ClassificationResult:
    """Classify a routing refusal the inference gateway raised on its own.

    Every member is ``CONFIGURATION``: nothing in the prompt, the parameters or the
    inputs causes any of these, and no edit to them avoids one. That is the whole
    point of the family — without it all four take the status ladder's 400 arm and
    read as a provider rejecting the caller's content.

    None is retryable, for the reason none of the other two gateway families is:
    the gateway refused before a provider saw the request, and an identical retry
    earns an identical refusal.
    """
    match refusal:
        case GatewayRoutingRefusal.UNKNOWN_MODEL:
            # The deployment does not know that model at all — which is exactly
            # what the ``is_model_not_found`` flag means, so this is the one member
            # that gets it. It selects the family's ``*ModelNotFoundError`` class,
            # which ``pipe_operator.py`` re-raises as a
            # ``PipeOperatorModelAvailabilityError`` carrying the model handle: the
            # same pipe-level error a caller gets when the deck itself cannot find
            # a model, which is this case seen from the gateway.
            return ClassificationResult(
                category=InferenceErrorCategory.CONFIGURATION,
                user_action_kind=UserActionKind.CHANGE_MODEL,
                is_model_not_found=True,
                gateway_routing_refusal=refusal,
            )
        case GatewayRoutingRefusal.WRONG_PROTOCOL | GatewayRoutingRefusal.UNSERVED_CAPABILITY:
            # The model exists and is served — it just cannot do what was asked, or
            # was asked over a protocol its integration does not speak. So the flag
            # stays unset: telling a caller the model was not found would be false,
            # and the Render step carries the real distinction. ``CHANGE_MODEL`` is
            # still what an end caller can do about it.
            return ClassificationResult(
                category=InferenceErrorCategory.CONFIGURATION,
                user_action_kind=UserActionKind.CHANGE_MODEL,
                gateway_routing_refusal=refusal,
            )
        case GatewayRoutingRefusal.DISABLED_INTEGRATION:
            # The integration is switched off because whoever operates the gateway
            # never set its credential. The deployment is what has to change, not
            # the request — so this is the family's ``CONTACT_SUPPORT`` arm, the
            # same call ``STORAGE_NOT_SERVED`` and ``BODY_LENGTH_REQUIRED`` get.
            # ``CHECK_CREDENTIALS`` would send a hosted caller to rotate their own
            # perfectly valid key; ``CHANGE_MODEL`` would send them shopping for a
            # model over an operator's unset variable. The flag stays unset: the
            # handle resolved, so this is not a model the deployment does not know.
            return ClassificationResult(
                category=InferenceErrorCategory.CONFIGURATION,
                user_action_kind=UserActionKind.CONTACT_SUPPORT,
                gateway_routing_refusal=refusal,
            )


def classify_inference_error(metadata: SDKErrorEnvelope) -> ClassificationResult:
    """Classify an inference SDK error from its structured metadata.

    Args:
        metadata: The structured envelope produced by a provider's
            ``extract_*_metadata`` function.

    Returns:
        A ``ClassificationResult`` carrying the error category, the user-action
        kind, and the model-not-found flag.
    """
    status_code = metadata.status_code

    if status_code is None:
        return _classify_statusless(metadata)

    # The inference gateway's own request-shape refusals come first: an explicit
    # code from a service we operate is a more specific verdict than any status
    # bucket, and the statuses they arrive on (413, 411, 400) would otherwise be
    # read as a provider rejecting the prompt. They cannot collide with the quota
    # rules below, which only fire on 402 and 429.
    gateway_request_limit = metadata.gateway_request_limit
    if gateway_request_limit is not None:
        return _classify_gateway_request_limit(limit=gateway_request_limit)

    # And its "cannot resolve this reference" refusals, for the same reason and on
    # the same footing. The two code sets are disjoint — a code names either a
    # bound the request exceeded or a reference that could not be resolved — so the
    # order between these two branches carries no meaning. Both arrive on 400,
    # which the status ladder would read as a provider rejecting the prompt.
    gateway_unresolved_reference = metadata.gateway_unresolved_reference
    if gateway_unresolved_reference is not None:
        return _classify_gateway_unresolved_reference(reference=gateway_unresolved_reference)

    # And its refusals to route the request at all, on the same footing again. All
    # three gateway code sets are disjoint, so the order among these branches
    # carries no meaning; what matters is that all three run ahead of the status
    # ladder. Every routing refusal arrives on 400, which the ladder would read as
    # a provider rejecting the prompt — for a model the gateway does not serve, is
    # not configured to reach, or cannot ask what was asked.
    gateway_routing_refusal = metadata.gateway_routing_refusal
    if gateway_routing_refusal is not None:
        return _classify_gateway_routing_refusal(refusal=gateway_routing_refusal)

    # Quota exhaustion is decided by the provider-aware ``is_quota_exhaustion``
    # property and takes precedence over the HTTP status: providers signal it on
    # different statuses (OpenAI/Anthropic 429, Mistral/Gateway 402, AWS 400).
    if metadata.is_quota_exhaustion:
        return ClassificationResult(
            category=InferenceErrorCategory.CAPACITY,
            user_action_kind=UserActionKind.CHECK_BILLING,
        )

    if status_code == 429:
        return ClassificationResult(
            category=InferenceErrorCategory.TRANSIENT,
            user_action_kind=UserActionKind.WAIT_AND_RETRY,
        )

    if status_code == 402:
        return ClassificationResult(
            category=InferenceErrorCategory.CAPACITY,
            user_action_kind=UserActionKind.CHECK_BILLING,
        )

    if status_code in {401, 403}:
        return ClassificationResult(
            category=InferenceErrorCategory.CONFIGURATION,
            user_action_kind=UserActionKind.CHECK_CREDENTIALS,
        )

    if status_code == 404:
        return ClassificationResult(
            category=InferenceErrorCategory.CONFIGURATION,
            user_action_kind=UserActionKind.CHANGE_MODEL,
            is_model_not_found=True,
        )

    if status_code == 400:
        return ClassificationResult(
            category=InferenceErrorCategory.CONTENT,
            user_action_kind=UserActionKind.CHANGE_INPUT,
        )

    if status_code >= 500:
        return ClassificationResult(
            category=InferenceErrorCategory.TRANSIENT,
            user_action_kind=UserActionKind.WAIT_AND_RETRY,
        )

    if status_code >= 400:
        # Unrecognized 4xx (e.g. 405, 409, 422) — 5xx is handled above. A safety/content
        # policy rejection routed as 422 (FAL surfaces these here, signalled by
        # ``provider_error_code = "ContentPolicyViolation"``) is rejected content, not a
        # configuration issue — keep it CONTENT so downstream reporting and retry policy
        # treat it as bad input.
        if metadata.is_content_policy_violation:
            return ClassificationResult(
                category=InferenceErrorCategory.CONTENT,
                user_action_kind=UserActionKind.CHANGE_INPUT,
            )
        return ClassificationResult(
            category=InferenceErrorCategory.CONFIGURATION,
            user_action_kind=UserActionKind.CHANGE_INPUT,
        )

    # A non-error status (< 400) on an error envelope: nothing we can classify.
    return ClassificationResult(
        category=InferenceErrorCategory.UNKNOWN,
        user_action_kind=UserActionKind.CONTACT_SUPPORT,
    )
