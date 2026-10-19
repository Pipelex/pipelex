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

The verdict carries the registry code the rendered error reports, beside the
category the runtime keeps for itself (retries, the Temporal activity's
``non_retryable``). The code depends on the family as well as the metadata in one
respect: a call that may have taken effect on the provider's side cannot be
repeated blind when it is not idempotent, so an image generation's 5xx, timeout
or dropped connection reads ``provider.outcome_unknown`` where a text call's
reads as an outage or a timeout.
"""

from enum import StrEnum
from typing import NamedTuple, Self

from mthds.protocol.problem.registry import CoreCode
from pydantic import BaseModel, model_validator

from pipelex.cogt.exceptions import INFERENCE_FAILURE_CODES, InferenceErrorCategory
from pipelex.cogt.inference.error_classification import SDKErrorEnvelope, UserActionKind
from pipelex.cogt.inference.service_error_vocabulary import ServiceErrorCode
from pipelex.errors.error_codes import ErrorCode, error_code_spec
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.runtime_hub import get_optional_service_error_vocabulary


class InferenceErrorFamily(StrEnum):
    """The worker family raising an inference error: selects the exception class, and whether a call may be repeated."""

    LLM = "llm"
    IMG_GEN = "img_gen"
    EXTRACT = "extract"
    SEARCH = "search"
    JUDGMENT = "judgment"

    @property
    def is_idempotent(self) -> bool:
        """Whether repeating a call that may have taken effect is harmless.

        An image generation is billed per image produced and its result is not kept by the provider for a
        repeat to find, so a call that may have run cannot be sent again blind. A text, extraction, search
        or judgment call answers the same question again.
        """
        match self:
            case InferenceErrorFamily.LLM | InferenceErrorFamily.EXTRACT | InferenceErrorFamily.SEARCH | InferenceErrorFamily.JUDGMENT:
                return True
            case InferenceErrorFamily.IMG_GEN:
                return False


class ClassificationResult(BaseModel):
    """Outcome of classifying an inference SDK error.

    ``is_model_not_found`` is a flag, not a category: the category stays
    ``CONFIGURATION`` for a missing model — only the rendered exception class
    differs (a ``*ModelNotFoundError`` rather than a generic failure error).
    """

    category: InferenceErrorCategory
    user_action_kind: UserActionKind
    # The registry code the rendered error reports: one of the codes every family's failure class declares
    # (``INFERENCE_FAILURE_CODES``), and ``model.unavailable`` whenever ``is_model_not_found`` selects the
    # family's not-found class.
    error_code: ErrorCode
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

    @model_validator(mode="after")
    def validate_error_code(self) -> Self:
        if self.error_code not in INFERENCE_FAILURE_CODES:
            msg = f"The classification's code '{self.error_code}' is not one an inference failure class declares"
            raise ValueError(msg)
        if self.is_model_not_found and self.error_code is not CoreCode.MODEL_UNAVAILABLE:
            msg = f"A model-not-found classification reports 'model.unavailable', not '{self.error_code}'"
            raise ValueError(msg)
        # The category decides whether the call is repeated within the run, the code whether the report invites a
        # retry: a call worth repeating cannot report a failure no retry clears.
        if self.category.is_retryable and not error_code_spec(self.error_code).invites_retry:
            msg = f"A {self.category} classification reports a code that invites a retry, not '{self.error_code}'"
            raise ValueError(msg)
        return self


class _StatuslessVerdict(NamedTuple):
    category: InferenceErrorCategory
    user_action_kind: UserActionKind
    error_code: ErrorCode


# Status-less SDK exception type names recognizable regardless of provider:
# the pydantic / instructor schema-validation failure and the uniquely-named
# Linkup typed exceptions (which carry no HTTP status). Network/transport
# failures are handled earlier via the metadata's ``is_network_error`` property.
_STATUSLESS_BY_TYPE_NAME: dict[str, _StatuslessVerdict] = {
    # pydantic / instructor schema-validation failure: the model's answer still did not fit the schema
    # after instructor's re-asks.
    "ValidationError": _StatuslessVerdict(InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT, CoreCode.MODEL_OUTPUT_SCHEMA_MISMATCH),
    # Linkup typed SDK exceptions. ``LinkupTimeoutError`` and any
    # connection-shaped variants flow through ``is_network_error`` (the
    # ``_NETWORK_ERROR_TOKENS`` check matches "timeout"/"connect"), so they are
    # intentionally absent from this map.
    "LinkupAuthenticationError": _StatuslessVerdict(
        InferenceErrorCategory.CONFIGURATION, UserActionKind.CHECK_CREDENTIALS, CoreCode.PROVIDER_CREDENTIAL_REFUSED
    ),
    "LinkupInsufficientCreditError": _StatuslessVerdict(
        InferenceErrorCategory.CAPACITY, UserActionKind.CHECK_BILLING, CoreCode.PROVIDER_QUOTA_EXHAUSTED
    ),
    "LinkupTooManyRequestsError": _StatuslessVerdict(InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY, CoreCode.PROVIDER_RATE_LIMITED),
    # A request Linkup could not take is one we built, so it is ours to fix rather than the caller's.
    "LinkupInvalidRequestError": _StatuslessVerdict(InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT, CoreCode.RUNTIME_UNEXPECTED),
    "LinkupNoResultError": _StatuslessVerdict(InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT, CoreCode.MODEL_NO_RESULT),
    "LinkupFetchResponseTooLargeError": _StatuslessVerdict(InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT, CoreCode.INPUT_TOO_LARGE),
    "LinkupFetchUrlIsFileError": _StatuslessVerdict(
        InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT, CoreCode.INPUT_FILE_TYPE_UNSUPPORTED
    ),
    # The page the caller named could not be fetched, which a later attempt may change.
    "LinkupFailedFetchError": _StatuslessVerdict(InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY, CoreCode.INPUT_URL_UNREACHABLE),
    "LinkupUnknownError": _StatuslessVerdict(InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY, CoreCode.PROVIDER_FAILED),
    # TypeSafe's client-side refusal: the SDK validates a request it will not send (an empty
    # questions map, a rating with no levels) and raises the bare base class, with no status, no
    # body and no request id. Every one of those is a shape our own blueprint validation is
    # supposed to have refused first, so it is a Pipelex defect rather than a vendor failure —
    # CONFIGURATION says nothing the caller wrote caused it and CONTACT_SUPPORT says who can fix
    # it. Its HTTP-reaching siblings (``TypeSafeAPITimeoutError``, ``TypeSafeAPIConnectionError``)
    # never arrive here: ``is_network_error`` matches their names first.
    "TypeSafeError": _StatuslessVerdict(InferenceErrorCategory.CONFIGURATION, UserActionKind.CONTACT_SUPPORT, CoreCode.RUNTIME_UNEXPECTED),
    # FAL's typed credential failure — raised before any HTTP call when the API key is unset
    "MissingCredentialsError": _StatuslessVerdict(
        InferenceErrorCategory.CONFIGURATION, UserActionKind.CHECK_CREDENTIALS, PipelexErrorCode.CONFIG_CREDENTIAL_MISSING
    ),
    # FAL's generic SDK error (base class) — caught last in the worker; HTTP/timeout variants
    # are peeled off earlier, so this branch represents the residual SDK failure. FAL serves image
    # generation alone, where ``_classify_statusless`` reads a failure that may have run as an
    # outcome nobody knows.
    "FalClientError": _StatuslessVerdict(InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY, CoreCode.PROVIDER_FAILED),
}

# Builtin exception type names raised by the local file-based extractors
# (docling, pypdfium2). Interpreted only when the provider is a local file
# extractor — the same builtin type means something else from an SDK provider.
_LOCAL_EXTRACT_BY_TYPE_NAME: dict[str, _StatuslessVerdict] = {
    "FileNotFoundError": _StatuslessVerdict(InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT, CoreCode.INPUT_REFERENCE_NOT_FOUND),
    # The file was there and did not parse.
    "ValueError": _StatuslessVerdict(InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT, CoreCode.INPUT_FILE_UNREADABLE),
    "RuntimeError": _StatuslessVerdict(InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT, CoreCode.INPUT_FILE_UNREADABLE),
    # A local disk or descriptor failure is this machine's, not the input's and not a provider's, and not one a retry
    # is known to clear.
    "OSError": _StatuslessVerdict(InferenceErrorCategory.UNKNOWN, UserActionKind.CONTACT_SUPPORT, CoreCode.RUNTIME_UNEXPECTED),
}

# The httpx transport failures that fire before a request leaves this process: the connection was never
# opened, or never taken from the pool. Nothing reached the provider, so even a call that is not
# idempotent may be sent again. Every other network failure may have fired after the provider took the
# request, an SDK's own ``APIConnectionError`` included, since it wraps a read as well as a connect.
_PRE_REQUEST_TRANSPORT_TYPE_NAMES: frozenset[str] = frozenset({"ConnectError", "ConnectTimeout", "PoolTimeout"})


def _outcome_unknown() -> ClassificationResult:
    """A call that is not idempotent and may have taken effect: not repeated by the runtime, the reader checks first."""
    return ClassificationResult(
        category=InferenceErrorCategory.AMBIGUOUS,
        user_action_kind=UserActionKind.WAIT_AND_RETRY,
        error_code=CoreCode.PROVIDER_OUTCOME_UNKNOWN,
    )


def _classify_network_error(*, metadata: SDKErrorEnvelope, family: InferenceErrorFamily) -> ClassificationResult:
    """Classify a failure that never reached an HTTP status: never sent, timed out, or dropped mid-request."""
    type_name = metadata.sdk_exception_type
    if type_name in _PRE_REQUEST_TRANSPORT_TYPE_NAMES:
        return ClassificationResult(
            category=InferenceErrorCategory.TRANSIENT,
            user_action_kind=UserActionKind.WAIT_AND_RETRY,
            error_code=CoreCode.PROVIDER_UNAVAILABLE,
        )
    if not family.is_idempotent:
        return _outcome_unknown()
    error_code: ErrorCode = CoreCode.PROVIDER_TIMEOUT if "timeout" in type_name.lower() else CoreCode.PROVIDER_UNAVAILABLE
    return ClassificationResult(
        category=InferenceErrorCategory.TRANSIENT,
        user_action_kind=UserActionKind.WAIT_AND_RETRY,
        error_code=error_code,
    )


def _classify_statusless(metadata: SDKErrorEnvelope, *, family: InferenceErrorFamily) -> ClassificationResult:
    """Classify an error that never reached an HTTP status (transport failure or local error)."""
    if metadata.is_network_error:
        return _classify_network_error(metadata=metadata, family=family)
    # The provider-agnostic map (pydantic / Linkup) takes precedence; the local
    # file-extractor map is a fallback applied only for docling / pypdfium2,
    # where builtins like ``ValueError`` carry an extraction-specific meaning.
    # The two maps share no type names, so precedence is currently moot.
    type_name = metadata.sdk_exception_type
    mapped = _STATUSLESS_BY_TYPE_NAME.get(type_name)
    if mapped is None and metadata.provider.is_local_file_extractor:
        mapped = _LOCAL_EXTRACT_BY_TYPE_NAME.get(type_name)
    if mapped is None:
        return ClassificationResult(
            category=InferenceErrorCategory.UNKNOWN,
            user_action_kind=UserActionKind.CONTACT_SUPPORT,
            error_code=CoreCode.RUNTIME_UNEXPECTED,
        )
    if mapped.category.is_retryable and not family.is_idempotent:
        # A residual SDK failure on a call that is not idempotent (FAL's ``FalClientError``) may have run.
        return _outcome_unknown()
    return ClassificationResult(category=mapped.category, user_action_kind=mapped.user_action_kind, error_code=mapped.error_code)


def _classify_server_error(*, status_code: int, family: InferenceErrorFamily) -> ClassificationResult:
    """Classify a provider 5xx: an outage, a timeout or a failure, unless the call may have run and cannot be repeated."""
    if not family.is_idempotent:
        return _outcome_unknown()
    error_code: ErrorCode
    match status_code:
        case 503 | 529:
            # 529 is Anthropic's "overloaded".
            error_code = CoreCode.PROVIDER_UNAVAILABLE
        case 504:
            error_code = CoreCode.PROVIDER_TIMEOUT
        case _:
            error_code = CoreCode.PROVIDER_FAILED
    return ClassificationResult(
        category=InferenceErrorCategory.TRANSIENT,
        user_action_kind=UserActionKind.WAIT_AND_RETRY,
        error_code=error_code,
    )


def classify_inference_error(metadata: SDKErrorEnvelope, *, family: InferenceErrorFamily) -> ClassificationResult:
    """Classify an inference SDK error from its structured metadata.

    Args:
        metadata: The structured envelope produced by a provider's
            ``extract_*_metadata`` function.
        family: The worker family that made the call, which says whether a call that may
            have run can be repeated.

    Returns:
        A ``ClassificationResult`` carrying the error category, the user-action
        kind, the registry code, and the model-not-found flag.
    """
    status_code = metadata.status_code

    if status_code is None:
        return _classify_statusless(metadata, family=family)

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
                error_code=service_error_code.error_code,
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
            error_code=CoreCode.MODEL_UNAVAILABLE,
            is_model_not_allowed=True,
        )

    # Quota exhaustion is decided by the provider-aware ``is_quota_exhaustion``
    # property and takes precedence over the HTTP status: providers signal it on
    # different statuses (OpenAI/Anthropic 429, Mistral/Gateway 402, AWS 400).
    if metadata.is_quota_exhaustion:
        return ClassificationResult(
            category=InferenceErrorCategory.CAPACITY,
            user_action_kind=UserActionKind.CHECK_BILLING,
            error_code=CoreCode.PROVIDER_QUOTA_EXHAUSTED,
        )

    if status_code == 429:
        return ClassificationResult(
            category=InferenceErrorCategory.TRANSIENT,
            user_action_kind=UserActionKind.WAIT_AND_RETRY,
            error_code=CoreCode.PROVIDER_RATE_LIMITED,
        )

    if status_code == 408:
        # The provider answered that it gave up waiting. Nothing in the caller's input or the deployment caused it,
        # and the provider said so itself, which is not the lost answer `provider.outcome_unknown` covers: the call
        # is repeated, a billed image call included.
        return ClassificationResult(
            category=InferenceErrorCategory.TRANSIENT,
            user_action_kind=UserActionKind.WAIT_AND_RETRY,
            error_code=CoreCode.PROVIDER_TIMEOUT,
        )

    if status_code == 402:
        return ClassificationResult(
            category=InferenceErrorCategory.CAPACITY,
            user_action_kind=UserActionKind.CHECK_BILLING,
            error_code=CoreCode.PROVIDER_QUOTA_EXHAUSTED,
        )

    if status_code in {401, 403}:
        return ClassificationResult(
            category=InferenceErrorCategory.CONFIGURATION,
            user_action_kind=UserActionKind.CHECK_CREDENTIALS,
            error_code=CoreCode.PROVIDER_CREDENTIAL_REFUSED,
        )

    if status_code == 404:
        # The deck names a provider model id the provider no longer serves: a method cannot name a raw
        # provider id, so this is never the method's `model.unknown`.
        return ClassificationResult(
            category=InferenceErrorCategory.CONFIGURATION,
            user_action_kind=UserActionKind.CHANGE_MODEL,
            error_code=CoreCode.MODEL_UNAVAILABLE,
            is_model_not_found=True,
        )

    if status_code == 400:
        # A 400 nothing recognises is most likely a request of ours the provider could not take; only a
        # content-policy signal says the caller's material was refused.
        return ClassificationResult(
            category=InferenceErrorCategory.CONTENT,
            user_action_kind=UserActionKind.CHANGE_INPUT,
            error_code=CoreCode.MODEL_CONTENT_REFUSED if metadata.is_content_policy_violation else CoreCode.RUNTIME_UNEXPECTED,
        )

    if status_code >= 500:
        return _classify_server_error(status_code=status_code, family=family)

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
                error_code=CoreCode.MODEL_CONTENT_REFUSED,
            )
        error_code: ErrorCode
        match status_code:
            case 413:
                # Anthropic's ``request_too_large``: the request the caller's material made is over the provider's limit.
                error_code = CoreCode.INPUT_TOO_LARGE
            case _:
                error_code = CoreCode.RUNTIME_UNEXPECTED
        return ClassificationResult(
            category=InferenceErrorCategory.CONFIGURATION,
            user_action_kind=UserActionKind.CHANGE_INPUT,
            error_code=error_code,
        )

    # A non-error status (< 400) on an error envelope: the provider's answer could not be used.
    return ClassificationResult(
        category=InferenceErrorCategory.UNKNOWN,
        user_action_kind=UserActionKind.CONTACT_SUPPORT,
        error_code=CoreCode.PROVIDER_RESPONSE_INVALID,
    )
