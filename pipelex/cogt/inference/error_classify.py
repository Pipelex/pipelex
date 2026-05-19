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


class ClassificationResult(BaseModel):
    """Outcome of classifying an inference SDK error.

    ``is_model_not_found`` is a flag, not a category: the category stays
    ``CONFIGURATION`` for a missing model — only the rendered exception class
    differs (a ``*ModelNotFoundError`` rather than a generic failure error).
    """

    category: InferenceErrorCategory
    user_action_kind: UserActionKind
    is_model_not_found: bool = False


# Status-less SDK exception type names recognizable regardless of provider:
# the pydantic / instructor schema-validation failure and the uniquely-named
# Linkup typed exceptions (which carry no HTTP status). Network/transport
# failures are handled earlier via the metadata's ``is_network_error`` property.
_STATUSLESS_BY_TYPE_NAME: dict[str, tuple[InferenceErrorCategory, UserActionKind]] = {
    # pydantic / instructor schema-validation failure
    "ValidationError": (InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
    # Linkup typed SDK exceptions
    "LinkupAuthenticationError": (InferenceErrorCategory.CONFIGURATION, UserActionKind.CHECK_CREDENTIALS),
    "LinkupInsufficientCreditError": (InferenceErrorCategory.CAPACITY, UserActionKind.CHECK_BILLING),
    "LinkupTooManyRequestsError": (InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY),
    "LinkupInvalidRequestError": (InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
    "LinkupNoResultError": (InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
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
        # Unrecognized 4xx (e.g. 405, 409, 422) — 5xx is handled above, so any
        # remaining >= 400 status is a non-retryable client/configuration error.
        return ClassificationResult(
            category=InferenceErrorCategory.CONFIGURATION,
            user_action_kind=UserActionKind.CHANGE_INPUT,
        )

    # A non-error status (< 400) on an error envelope: nothing we can classify.
    return ClassificationResult(
        category=InferenceErrorCategory.UNKNOWN,
        user_action_kind=UserActionKind.CONTACT_SUPPORT,
    )
