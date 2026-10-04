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
from pipelex.cogt.inference.error_classification import SDKErrorEnvelope, UserActionKind
from pipelex.cogt.inference.service_error_vocabulary import ServiceErrorCode
from pipelex.runtime_hub import get_optional_service_error_vocabulary


class ClassificationResult(BaseModel):
    """Outcome of classifying an inference SDK error.

    ``is_model_not_found`` is a flag, not a category: the category stays
    ``CONFIGURATION`` for a missing model — only the rendered exception class
    differs (a ``*ModelNotFoundError`` rather than a generic failure error).
    """

    category: InferenceErrorCategory
    user_action_kind: UserActionKind
    is_model_not_found: bool = False
    # The service error code this refusal carried, when the service the request reached refused it
    # itself under a code its plugin contributed (see ``service_error_vocabulary``). Like
    # ``is_model_not_found`` this is a flag rather than a category: the entry already decided the
    # category and the action, and it lets the Render step give the entry's own advice instead of
    # falling back to the generic "the provider rejected the request".
    service_error_code: ServiceErrorCode | None = None
    # Whether an integration serves the model but does not allow it for this caller. A flag for the
    # same reason: the model exists and is served, so it is not a model-not-found, and the Render step
    # names the model handle the deck resolved to, which the refusal's own message does not.
    is_model_not_allowed: bool = False


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
    # TypeSafe's client-side refusal: the SDK validates a request it will not send (an empty
    # questions map, a rating with no levels) and raises the bare base class, with no status, no
    # body and no request id. Every one of those is a shape our own blueprint validation is
    # supposed to have refused first, so it is a Pipelex defect rather than a vendor failure —
    # CONFIGURATION says nothing the caller wrote caused it and CONTACT_SUPPORT says who can fix
    # it. Its HTTP-reaching siblings (``TypeSafeAPITimeoutError``, ``TypeSafeAPIConnectionError``)
    # never arrive here: ``is_network_error`` matches their names first.
    "TypeSafeError": (InferenceErrorCategory.CONFIGURATION, UserActionKind.CONTACT_SUPPORT),
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

    # A code the service contributed comes first: an explicit code from the service itself is a
    # more specific verdict than any status bucket, and the statuses such refusals arrive on (413,
    # 411, 400) would otherwise be read as a provider rejecting the prompt. The vocabulary is the
    # booted plugins' (see ``service_error_vocabulary``); a process that registered none classifies
    # on the status ladder alone.
    vocabulary = get_optional_service_error_vocabulary()
    if vocabulary is not None:
        service_error_code = vocabulary.lookup(code=metadata.provider_error_code)
        if service_error_code is not None:
            return ClassificationResult(
                category=service_error_code.category,
                user_action_kind=service_error_code.user_action_kind,
                is_model_not_found=service_error_code.is_model_not_found,
                service_error_code=service_error_code,
            )

    # A model an integration serves but does not allow for this caller, on the same footing. It
    # arrives on 412, which the ladder's generic 4xx arm would send to the prompt, the parameters and
    # the inputs. Nothing in those causes it: the model exists and is served, only not for this
    # caller, so the flag stays unset and ``CHANGE_MODEL`` is what an end caller can do about it.
    if metadata.is_model_not_allowed:
        return ClassificationResult(
            category=InferenceErrorCategory.CONFIGURATION,
            user_action_kind=UserActionKind.CHANGE_MODEL,
            is_model_not_allowed=True,
        )

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
