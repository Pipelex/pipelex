"""Helpers for classifying SDK errors into InferenceErrorCategory values.

Pure functions that inspect error messages to discriminate between
quota exhaustion vs rate limiting, detect content policy violations, and
recover the underlying SDK exception that ``InstructorRetryException``
wraps when ``instructor`` exhausts its retry loop.
"""

import json
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from enum import StrEnum
from typing import Any, TypeAlias, cast

import httpx
from pydantic import BaseModel, Field

from pipelex.cogt.inference.provider_name import ProviderName

# SDK exception class-name substrings that identify a network/transport failure
# (no HTTP status reached us). Matched case-insensitively against
# ``sdk_exception_type`` — covers httpx transport errors, SDK timeout/connection
# errors, Mistral's ``NoResponseError``, and builtin ``TimeoutError``.
_NETWORK_ERROR_TOKENS: tuple[str, ...] = ("timeout", "connect", "transport", "noresponse")

# ``httpx.TransportError`` subclass names whose class names contain none of the
# ``_NETWORK_ERROR_TOKENS`` and therefore would otherwise fall through to
# UNKNOWN. These can reach a provider's extract_* helper directly (Azure REST
# uses raw httpx; OpenAI / Anthropic / Gateway SDKs may also surface them when
# their connection wrappers are bypassed) without going through the
# ``_resolve_sdk_exception_type`` normalization, so we recognize them by name
# here to keep transport failures classified as TRANSIENT.
_STATUSLESS_TRANSPORT_TYPE_NAMES: frozenset[str] = frozenset(
    {
        "TransportError",
        "ReadError",
        "WriteError",
        "CloseError",
        "RemoteProtocolError",
        "ProxyError",
        "UnsupportedProtocol",
        "NetworkError",
    }
)


class GatewayRequestLimit(StrEnum):
    """A request-shape refusal raised by the Pipelex inference gateway itself.

    The gateway bounds what a request may weigh and how deeply it may nest, and
    refuses anything over those bounds *before* the request reaches a provider —
    the body cap and the length rule run ahead of authentication, on the headers
    alone. Those refusals are not inference failures and must not read as one: a
    caller who sent something too large has a limit to respect, not a prompt to
    revise, and nothing about a retry can help.

    Each member corresponds to one of the gateway's own error codes, which is the
    contract between the two repositories — the wording of a refusal is free to
    change, the code is not.
    """

    #: ``pig-07`` at HTTP 413 — the declared body size is over the gateway's cap
    #: for its media type (JSON or multipart).
    BODY_TOO_LARGE = "body_too_large"
    #: ``pig-08`` at HTTP 411 — the body's size cannot be read at all: a chunked
    #: body, or a ``Content-Length`` that is not a byte count. No HTTP client the
    #: runtime uses produces this; it exists so that an unusual one fails closed
    #: and legibly rather than being buffered to find out how big it is.
    BODY_LENGTH_REQUIRED = "body_length_required"
    #: HTTP 413 — a file the request only *refers* to is over its cap: a
    #: ``pipelex-storage://`` object the gateway resolved, or a document it
    #: fetched by URL. The same "too large" family as ``BODY_TOO_LARGE``, one
    #: indirection further out. It arrives under three codes because the gateway
    #: renders the same failure twice — ``pig-10`` on the LLM routes, where its
    #: own ``pig-0N`` family is the only vocabulary available, and
    #: ``pipelex_storage_object_too_large`` / ``pipelex_document_too_large`` on
    #: the native ``/v1/pipelex/*`` routes, whose wire contract is its own.
    OBJECT_TOO_LARGE = "object_too_large"
    #: ``pig-11`` at HTTP 400 — the parsed body nests deeper than the gateway's
    #: depth limit. Not a byte question: nesting costs two bytes a level, so a
    #: body well under any size cap can still overflow a walker.
    BODY_TOO_DEEP = "body_too_deep"


# The gateway's error codes, mapped to what the runtime does about them.
#
# **Matched on the code alone, with no check on ``provider``**, and that is the
# design rather than an omission. A request reaches the gateway through whichever
# SDK its dialect calls for — the Portkey substrate (reported as ``GATEWAY``),
# plain ``httpx`` on the native extract/search routes (``GATEWAY`` as well), and
# the shared Anthropic driver that Claude travels on (reported as ``ANTHROPIC``) —
# so the reporting provider does not identify the gateway. ``pig-`` and
# ``pipelex_`` are both the gateway's own code namespaces and no vendor emits into
# either, so the code alone is both necessary and sufficient.
#
# **One failure can appear under two codes**, and leaving out the second one is
# how a caller reads "the provider rejected the request" for a file they can
# simply make smaller. The gateway renders a refusal in the vocabulary of the
# route it arrived on: its own ``pig-0N`` family on the LLM routes, where the
# client is speaking a provider's protocol, and its frozen ``pipelex_*`` contract
# codes on the native ``/v1/pipelex/*`` extract and search routes. A new limit has
# to be looked for in both.
_GATEWAY_REQUEST_LIMIT_BY_CODE: dict[str, GatewayRequestLimit] = {
    "pig-07": GatewayRequestLimit.BODY_TOO_LARGE,
    "pig-08": GatewayRequestLimit.BODY_LENGTH_REQUIRED,
    "pig-10": GatewayRequestLimit.OBJECT_TOO_LARGE,
    "pig-11": GatewayRequestLimit.BODY_TOO_DEEP,
    # The native routes' rendering of the same "over its cap" refusal: a storage
    # object the gateway resolved, and a document it fetched by URL.
    "pipelex_storage_object_too_large": GatewayRequestLimit.OBJECT_TOO_LARGE,
    "pipelex_document_too_large": GatewayRequestLimit.OBJECT_TOO_LARGE,
}


class GatewayUnresolvedReference(StrEnum):
    """A "cannot resolve this reference" refusal raised by the Pipelex inference gateway itself.

    A request may name a file rather than carry it — a ``pipelex-storage://`` key
    the gateway resolves for the caller, or a document URL it fetches on their
    behalf. When it cannot turn that reference into bytes it refuses the request
    itself, before a provider sees it. Like the request-shape limits these are not
    inference failures and must not read as one: a caller who mistyped a storage
    key, pointed at an object this deployment cannot read, or aimed a URL at a host
    the gateway will not fetch from has a *reference* to fix, not a prompt to
    revise, and nothing about a retry can help.

    The members group by remedy rather than by wire code: two codes share a member
    only when the caller's next move is the same. Every member defers the specifics
    — the key, the host, the status, the media type — to the gateway's own refusal
    message, which already names them.

    Each member corresponds to one or more of the gateway's own error codes, which
    is the contract between the two repositories — the wording of a refusal is free
    to change, the code is not.
    """

    #: ``pig-09`` at HTTP 400 — the LLM routes' single fail-closed slot for "this
    #: reference cannot be resolved". Every storage failure but "over its cap"
    #: arrives under it (no bucket configured, not a storage reference, no such
    #: object, an object that cannot be read, a type no provider takes, no way to
    #: hand a file to the provider this model resolves to) because there the client
    #: speaks a provider's protocol and the gateway's own ``pig-0N`` family is the
    #: only vocabulary available. The message carries the difference; the code does
    #: not, so the advice defers to it.
    REFERENCE_UNRESOLVED = "reference_unresolved"
    #: ``pipelex_storage_uri_invalid`` at HTTP 400 — the reference does not obey the
    #: key grammar (the path-traversal guard refuses under the same code).
    STORAGE_REFERENCE_INVALID = "storage_reference_invalid"
    #: ``pipelex_storage_unreadable`` at HTTP 400 — the object is not there, or the
    #: gateway's role may not read it. Deliberately one member: the gateway does not
    #: tell a caller which of the two it was, and neither may we.
    STORAGE_OBJECT_UNREADABLE = "storage_object_unreadable"
    #: ``pipelex_storage_uri_unsupported`` at HTTP 400 — no bucket is configured, so
    #: this deployment does not serve ``pipelex-storage://`` references at all.
    #: Nothing about the inputs causes it: it is an operator's problem.
    STORAGE_NOT_SERVED = "storage_not_served"
    #: HTTP 400 — the document URL was refused before or during the fetch, on its
    #: form rather than on what it served: ``pipelex_unsupported_uri_scheme`` (a
    #: scheme the route does not read) and ``pipelex_document_scheme_refused`` (the
    #: fetch's own check, reachable only for an unparseable URL now that the route
    #: admits ``https:`` alone), ``pipelex_document_address_refused`` (the resolved
    #: address is not publicly routable) and ``pipelex_document_redirect_refused``
    #: (the origin answered a redirect, which the gateway will not follow).
    DOCUMENT_URL_REFUSED = "document_url_refused"
    #: ``pipelex_document_host_refused`` at HTTP 400 — the gateway's SSRF guard
    #: refuses to fetch documents from this host. Its own member rather than a share
    #: of ``DOCUMENT_URL_REFUSED`` because the advice has to state a deliberate
    #: security policy: the caller can act, but nothing about their document is at
    #: fault and no amount of reshaping it will help.
    DOCUMENT_HOST_REFUSED = "document_host_refused"
    #: ``pipelex_document_unreachable`` at HTTP 400 — the origin answered a
    #: non-success status. Not retried: the gateway renders it 400, a retry would
    #: re-run a whole inference call to re-fetch the document, and the common case
    #: is a URL that is simply wrong.
    DOCUMENT_UNREACHABLE = "document_unreachable"
    #: HTTP 400 — the document was fetched, and what came back cannot be used:
    #: ``pipelex_document_empty`` (served empty), ``pipelex_document_unsupported_type``
    #: (a media type the pipeline does not accept) and ``pipelex_document_bad_data_url``
    #: (a ``data:`` URL that cannot be decoded).
    DOCUMENT_CONTENT_UNUSABLE = "document_content_unusable"


# The gateway's unresolvable-reference codes, mapped to what the runtime does
# about them.
#
# **Matched on the code alone, with no check on ``provider``**, for exactly the
# reason ``_GATEWAY_REQUEST_LIMIT_BY_CODE`` is: the reporting provider does not
# identify the gateway (three SDK hops report three provider names), while ``pig-``
# and ``pipelex_`` are the gateway's own code namespaces and no vendor emits into
# either.
#
# **Disjoint from the request-limit map by construction.** The two families answer
# different questions — one bounds the request's shape, the other says a reference
# could not be resolved — and a code belongs to exactly one of them. ``pig-09`` and
# ``pig-10`` are the clearest illustration: the same middleware raises both, one
# when the object is over its cap and one when it cannot be resolved at all.
_GATEWAY_UNRESOLVED_REFERENCE_BY_CODE: dict[str, GatewayUnresolvedReference] = {
    "pig-09": GatewayUnresolvedReference.REFERENCE_UNRESOLVED,
    # The native ``/v1/pipelex/*`` routes' own contract codes, where the gateway
    # names each cause instead of folding them into one fail-closed slot.
    "pipelex_storage_uri_invalid": GatewayUnresolvedReference.STORAGE_REFERENCE_INVALID,
    "pipelex_storage_unreadable": GatewayUnresolvedReference.STORAGE_OBJECT_UNREADABLE,
    "pipelex_storage_uri_unsupported": GatewayUnresolvedReference.STORAGE_NOT_SERVED,
    "pipelex_document_scheme_refused": GatewayUnresolvedReference.DOCUMENT_URL_REFUSED,
    # The scheme refusal a caller actually reaches. ``classifyExtractInput`` runs
    # before any fetch and admits only ``https:``, ``data:`` and
    # ``pipelex-storage://``, so an ``http://`` URL is refused here rather than by
    # the fetch above — which by then can only see URLs that already start with
    # ``https://``.
    "pipelex_unsupported_uri_scheme": GatewayUnresolvedReference.DOCUMENT_URL_REFUSED,
    "pipelex_document_address_refused": GatewayUnresolvedReference.DOCUMENT_URL_REFUSED,
    "pipelex_document_redirect_refused": GatewayUnresolvedReference.DOCUMENT_URL_REFUSED,
    "pipelex_document_host_refused": GatewayUnresolvedReference.DOCUMENT_HOST_REFUSED,
    "pipelex_document_unreachable": GatewayUnresolvedReference.DOCUMENT_UNREACHABLE,
    "pipelex_document_empty": GatewayUnresolvedReference.DOCUMENT_CONTENT_UNUSABLE,
    "pipelex_document_unsupported_type": GatewayUnresolvedReference.DOCUMENT_CONTENT_UNUSABLE,
    "pipelex_document_bad_data_url": GatewayUnresolvedReference.DOCUMENT_CONTENT_UNUSABLE,
}


class GatewayRoutingRefusal(StrEnum):
    """A "cannot route this request" refusal raised by the Pipelex inference gateway itself.

    Before a request can reach a provider the gateway has to decide *which*
    provider — it reads the model out of the request, looks it up in its own
    routing table, and hands the call to the integration that serves it. When
    that resolution fails it refuses the request itself, with codes of its own.
    These are not inference failures and must not read as one: a caller who named
    a model this deployment does not serve has a *model* to change or a
    deployment to fix, not a prompt to revise, and nothing about a retry can help.

    Every member is its own wire code here, unlike the two families beside it —
    not by accident but because each names a different thing that has to change.
    The one they nearly share is the flag: ``UNKNOWN_MODEL`` is the only member
    that means "this deployment does not know that model", so it is the only one
    the Classify step renders as a ``*ModelNotFoundError``.

    Each member corresponds to one of the gateway's own error codes, which is the
    contract between the two repositories — the wording of a refusal is free to
    change, the code is not.
    """

    #: ``pig-01`` at HTTP 400 — the request body names no model at all, or names
    #: one that no integration this deployment carries lists. Reached from the
    #: runtime by a model deck whose handle the gateway does not serve: a stale
    #: deck, a typo in a ``.mthds`` file's model, or a model the deployment
    #: deliberately does not carry.
    UNKNOWN_MODEL = "unknown_model"
    #: ``pig-02`` at HTTP 400 — the model resolves, but to an integration the
    #: deployment has switched off because a credential variable is unset. Nothing
    #: about the request causes it and no request avoids it: the gateway's own
    #: message names the integration and the variables whoever operates it must
    #: set.
    DISABLED_INTEGRATION = "disabled_integration"
    #: ``pig-05`` at HTTP 400 — a native-protocol path names a model that another
    #: provider serves. Today that is only Google's
    #: ``/v1beta/models/<model>:generateContent`` shape, the one
    #: ``nativeProtocolPaths.ts`` admits. Reaching it means the model deck and the
    #: gateway disagree about which backend serves a model: the model exists and
    #: is served, just not over the protocol the runtime spoke to ask for it.
    WRONG_PROTOCOL = "wrong_protocol"
    #: ``pig-06`` at HTTP 400 — a model reached one of the native
    #: ``/v1/pipelex/*`` routes (extract, search) whose integration's provider does
    #: not serve that capability. Again a deck-versus-gateway disagreement, or a
    #: model named on a pipe it cannot serve: the message names the integration,
    #: the provider and the capability.
    UNSERVED_CAPABILITY = "unserved_capability"


# The gateway's routing-refusal codes, mapped to what the runtime does about them.
#
# **Matched on the code alone, with no check on ``provider``**, for exactly the
# reason the two maps above are: the reporting provider does not identify the
# gateway. These arrive under more than one ``ProviderName`` — the Portkey
# substrate and the OpenAI substrate that carries every chat call both report
# ``GATEWAY``, plain ``httpx`` on the native routes reports ``GATEWAY`` too, and
# Claude travels on the shared Anthropic driver — while ``pig-`` is the gateway's
# own code namespace and no vendor emits into it.
#
# **Two of the gateway's routing codes are deliberately absent**, and the omission
# is the scope decision rather than an oversight:
#
# - ``pig-03`` ("the client tried to route") refuses a ``x-portkey-*`` steering
#   header, the ``?model=`` query form, a ``@<slug>/<model>`` virtual-key model, or
#   a path and body naming different models. No client the runtime ships produces
#   any of those — ``tests/unit/pipelex/providers/manifold/test_manifold_clients.py``
#   pins that — so reaching it means a client bug, not a caller's or an operator's
#   mistake, and the status ladder's reading is as good as any.
# - ``pig-04`` ("this gateway does not serve ``<method> <path>``") is the proxy
#   policy refusing a path only the catch-all could answer, and it is a 404, so the
#   ladder already reads it as model-not-found — wrong in kind, but unreachable
#   while the runtime calls only the routes the gateway mounts, and a served-path
#   drift is a deployment bug to surface loudly rather than a verdict to soften.
#
# ``pig-09`` is not a routing refusal either: it belongs to the
# unresolvable-reference family, which ``_GATEWAY_UNRESOLVED_REFERENCE_BY_CODE``
# reads.
_GATEWAY_ROUTING_REFUSAL_BY_CODE: dict[str, GatewayRoutingRefusal] = {
    "pig-01": GatewayRoutingRefusal.UNKNOWN_MODEL,
    "pig-02": GatewayRoutingRefusal.DISABLED_INTEGRATION,
    "pig-05": GatewayRoutingRefusal.WRONG_PROTOCOL,
    "pig-06": GatewayRoutingRefusal.UNSERVED_CAPABILITY,
}


def _resolve_sdk_exception_type(exc: BaseException, *, status_code: int | None) -> str:
    """Return the ``sdk_exception_type`` name, normalizing status-less httpx transport errors.

    Some ``httpx.TransportError`` subclasses (``ReadError``, ``WriteError``,
    ``CloseError``, ``RemoteProtocolError``, ``ProxyError``, ``UnsupportedProtocol``,
    ``NetworkError``) have names that contain none of the recognized
    ``_NETWORK_ERROR_TOKENS``, so without normalization the classifier would treat
    them as ``UNKNOWN`` instead of transient transport failures. We surface them
    as ``"TransportError"`` only when the original name lacks a recognized token —
    ``ConnectError`` / ``ReadTimeout`` / ``ConnectTimeout`` etc. already match
    and stay unchanged so their semantic stays in the metadata.
    """
    raw = type(exc).__name__
    if status_code is None and isinstance(exc, httpx.TransportError):
        if not any(token in raw.lower() for token in _NETWORK_ERROR_TOKENS):
            return "TransportError"
    return raw


class ProviderErrorMetadata(BaseModel):
    """Structured SDK metadata attached to inference errors.

    Carries information downstream consumers (retry, temporal, CLI) need
    without having to scrape it back from the exception chain.
    """

    provider: ProviderName
    sdk_exception_type: str
    # Human-readable error text from the SDK exception (``str(exc)``). Both the
    # Classify step (quota / content-policy discrimination) and the Render step
    # (message composition) read it, so the Extract step must capture it.
    message: str = ""
    status_code: int | None = None
    request_id: str | None = None
    retry_after_seconds: float | None = None
    provider_error_code: str | None = None
    # Raw provider response body — can carry account ids, billing details, or
    # credential fragments, so it is excluded from serialization (CLI JSON,
    # agent output, Temporal error details) while staying available in-process.
    body: Any | None = Field(default=None, exclude=True)

    @property
    def is_quota_exhaustion(self) -> bool:
        """Whether this error is a quota/credits exhaustion rather than rate limiting.

        Dispatches on ``provider`` because each provider phrases quota
        exhaustion differently; Mistral and Gateway also use HTTP 402.
        """
        match self.provider:
            case ProviderName.OPENAI:
                return _is_quota_exhaustion_openai(self.message)
            case ProviderName.ANTHROPIC:
                return _is_quota_exhaustion_anthropic(self.message)
            case ProviderName.GOOGLE:
                return _is_quota_exhaustion_google(self.message)
            case ProviderName.MISTRAL:
                return _is_quota_exhaustion_mistral(self.message, status_code=self.status_code or 0)
            case ProviderName.BEDROCK:
                return _is_quota_exhaustion_aws(self.message, provider_error_code=self.provider_error_code)
            case ProviderName.GATEWAY:
                return _is_quota_exhaustion_gateway(self.message, status_code=self.status_code or 0)
            case (
                ProviderName.AZURE | ProviderName.FAL | ProviderName.HUGGINGFACE | ProviderName.LINKUP | ProviderName.DOCLING | ProviderName.PYPDFIUM2
            ):
                return False

    @property
    def gateway_request_limit(self) -> GatewayRequestLimit | None:
        """Which of the gateway's request-shape limits this refusal hit, if any.

        Reads ``provider_error_code``, which every Extract hop that can carry a
        gateway refusal populates: the shared Anthropic driver recovers it from the
        ``{"error": {"code": …}}`` body the gateway renders, the OpenAI substrate
        reads the same value off ``exc.code`` after its SDK pre-unwraps that body,
        and the Portkey substrate re-parses the response because its SDK replaces
        ``exc.body`` with the message string (see ``extract_gateway_metadata``).

        Returns ``None`` for every other refusal — including the gateway's "cannot
        resolve this reference" codes and its routing refusals, each a separate
        family read by ``gateway_unresolved_reference`` and
        ``gateway_routing_refusal``.
        """
        if self.provider_error_code is None:
            return None
        return _GATEWAY_REQUEST_LIMIT_BY_CODE.get(self.provider_error_code)

    @property
    def gateway_unresolved_reference(self) -> GatewayUnresolvedReference | None:
        """Which of the gateway's unresolvable-reference refusals this is, if any.

        Reads ``provider_error_code`` off the same Extract hops
        ``gateway_request_limit`` does, and for the same reason: a request that
        names a file rather than carrying it can be refused by the gateway before
        any provider sees it, and the code is the only thing that says so.

        The three gateway families are disjoint — a code names a bound the request
        exceeded, a reference that could not be resolved, or a request that could
        not be routed, never two of them — so the Classify step may read them in
        any order. Returns ``None`` for every other refusal, the gateway's routing
        codes included.
        """
        if self.provider_error_code is None:
            return None
        return _GATEWAY_UNRESOLVED_REFERENCE_BY_CODE.get(self.provider_error_code)

    @property
    def gateway_routing_refusal(self) -> GatewayRoutingRefusal | None:
        """Which of the gateway's routing refusals this is, if any.

        Reads ``provider_error_code`` off the same Extract hops the two properties
        above do, and for the same reason: the gateway can refuse to route a
        request before any provider sees it, and the code is the only thing that
        says so. Without this the whole family falls through to the status ladder's
        400 arm and a caller who named a model the deployment does not serve is
        told to review their prompt.

        Disjoint from both other families by construction, so the Classify step may
        read the three in any order. Returns ``None`` for every other refusal,
        including the gateway's own ``pig-03`` and ``pig-04``, which the runtime's
        own clients cannot produce (see ``_GATEWAY_ROUTING_REFUSAL_BY_CODE``).
        """
        if self.provider_error_code is None:
            return None
        return _GATEWAY_ROUTING_REFUSAL_BY_CODE.get(self.provider_error_code)

    @property
    def is_content_policy_violation(self) -> bool:
        """Whether the error indicates a content policy / safety filter violation.

        Checks the structured ``provider_error_code`` (e.g. FAL surfaces
        ``ContentPolicyViolation`` here without echoing it into the message),
        the rendered ``message``, and the in-process ``body`` payload. ``body``
        is scanned because Azure REST returns the safety phrasing only in the
        response body — never in the ``HTTPStatusError`` message — and ``body``
        is ``exclude=True`` on serialization so the scan stays in-process.
        """
        if self.provider_error_code and "contentpolicy" in self.provider_error_code.lower():
            return True
        if _is_content_policy_violation(self.message):
            return True
        return self.body is not None and _is_content_policy_violation(_stringify_for_scan(self.body))

    @property
    def is_network_error(self) -> bool:
        """Whether this is a network/transport failure that never reached an HTTP status."""
        if self.status_code is not None:
            return False
        if self.sdk_exception_type in _STATUSLESS_TRANSPORT_TYPE_NAMES:
            return True
        lowered = self.sdk_exception_type.lower()
        return any(token in lowered for token in _NETWORK_ERROR_TOKENS)


# Readable alias for the Classify / Render pipeline: the metadata model is the
# structured envelope those steps consume.
SDKErrorEnvelope: TypeAlias = ProviderErrorMetadata


class UserActionKind(StrEnum):
    """Discrete categories of advice we surface to the user/agent.

    Lets the CLI render consistent guidance and agent JSON stay typed across
    providers. The free-form ``detail`` string carries provider-specific text.
    """

    WAIT_AND_RETRY = "wait_and_retry"
    CHECK_BILLING = "check_billing"
    CHECK_CREDENTIALS = "check_credentials"
    CHANGE_INPUT = "change_input"
    CHANGE_MODEL = "change_model"
    CONTACT_SUPPORT = "contact_support"
    UNKNOWN = "unknown"


class UserAction(BaseModel):
    """Structured user-facing advice attached to an inference error.

    ``kind`` discriminates the type of action, ``detail`` is the free-form
    provider-specific advice (e.g. a billing URL, a retry hint).
    """

    kind: UserActionKind
    detail: str


_OPENAI_QUOTA_PATTERNS: tuple[str, ...] = (
    "insufficient_quota",
    "exceeded your current quota",
)

_ANTHROPIC_QUOTA_PATTERNS: tuple[str, ...] = (
    "quota exceeded",
    "quota has been",
    "credit balance",
    "out of credits",
    "insufficient credit",
    "billing limit",
    "billing issue",
)

_CONTENT_POLICY_PATTERNS: tuple[str, ...] = (
    "content_policy",
    "content_filter",
    "safety system",
    "safety filter",
    "blocked by safety",
)

_GOOGLE_QUOTA_PATTERNS: tuple[str, ...] = (
    "quota exceeded",
    "resource has been exhausted",
    "billing limit",
    "billing quota",
    "billing exceeded",
    "billing account",
)

_MISTRAL_QUOTA_PATTERNS: tuple[str, ...] = (
    "quota",
    "billing limit",
    "billing quota",
    "out of credits",
    "insufficient credits",
)

_AWS_QUOTA_PATTERNS: tuple[str, ...] = (
    "quota",
    "limit exceeded",
    "service quota",
)

_GATEWAY_QUOTA_PATTERNS: tuple[str, ...] = (
    "quota",
    "billing limit",
    "billing quota",
    "insufficient_quota",
    "insufficient credit",
    "insufficient funds",
    "insufficient balance",
    "credits exhausted",
)


def _is_quota_exhaustion_openai(error_message: str) -> bool:
    """Check if an OpenAI error message indicates quota/credits exhaustion rather than rate limiting."""
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _OPENAI_QUOTA_PATTERNS)


def _is_quota_exhaustion_anthropic(error_message: str) -> bool:
    """Check if an Anthropic error message indicates quota/credits exhaustion rather than rate limiting."""
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _ANTHROPIC_QUOTA_PATTERNS)


def _is_quota_exhaustion_google(error_message: str) -> bool:
    """Check if a Google error message indicates quota/credits exhaustion rather than rate limiting."""
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _GOOGLE_QUOTA_PATTERNS)


def _is_quota_exhaustion_mistral(error_message: str, *, status_code: int) -> bool:
    """Check if a Mistral error indicates quota/credits exhaustion.

    HTTP 402 (Payment Required) is a definitive quota signal.
    HTTP 429 requires message inspection to distinguish quota from rate limiting.
    """
    if status_code == 402:
        return True
    lower_message = error_message.lower()
    return status_code == 429 and any(pattern in lower_message for pattern in _MISTRAL_QUOTA_PATTERNS)


def _is_quota_exhaustion_aws(error_message: str, *, provider_error_code: str | None) -> bool:
    """Check if an AWS error indicates quota/credits exhaustion rather than rate limiting.

    AWS botocore puts the canonical signal in the error ``Code`` (e.g.
    ``ServiceQuotaExceededException``), which ``extract_bedrock_metadata`` surfaces
    as ``provider_error_code``. Some payloads also echo the situation in the
    ``Message`` text — we check both so a quota exception with a vague message is
    still detected.
    """
    if provider_error_code == "ServiceQuotaExceededException":
        return True
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _AWS_QUOTA_PATTERNS)


def _is_quota_exhaustion_gateway(error_message: str, *, status_code: int) -> bool:
    """Check if a Portkey/Gateway error indicates quota/credits exhaustion.

    HTTP 402 (Payment Required) is a definitive quota signal.
    HTTP 429 requires message inspection to distinguish quota from rate limiting.
    """
    if status_code == 402:
        return True
    lower_message = error_message.lower()
    return status_code == 429 and any(pattern in lower_message for pattern in _GATEWAY_QUOTA_PATTERNS)


def _is_content_policy_violation(error_message: str) -> bool:
    """Check if an error message indicates a content policy or safety filter violation."""
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _CONTENT_POLICY_PATTERNS)


def _stringify_for_scan(body: Any) -> str:
    """Render a metadata body into a lowercase string for content-policy / quota probing.

    Used only by in-process scanners that need to inspect the response payload; the
    return value is never surfaced to users (``body`` is ``exclude=True``).
    """
    if isinstance(body, str):
        return body
    try:
        return json.dumps(body, default=str)
    except (TypeError, ValueError):
        return str(body)


def extract_underlying_sdk_exception(instructor_exc: Any) -> BaseException | None:
    """Recover the SDK exception that caused an ``InstructorRetryException``.

    instructor's retry loop wraps the last failed attempt's exception inside
    ``InstructorRetryException``. We prefer ``failed_attempts[-1].exception``
    (the documented public attribute) and fall back to walking ``__cause__``
    (a tenacity ``RetryError`` whose ``last_attempt._exception`` holds the
    original exception) when ``failed_attempts`` is unset.

    Args:
        instructor_exc: The ``InstructorRetryException`` to unwrap. Typed as
            ``Any`` so callers don't need to import ``InstructorRetryException``
            just for the call site, and so malformed inputs are tolerated.

    Returns:
        The underlying SDK exception when one can be recovered, ``None`` when
        neither path yields a ``BaseException``.
    """
    failed_attempts: Any = getattr(instructor_exc, "failed_attempts", None)
    if failed_attempts:
        try:
            last_attempt = failed_attempts[-1]
        except (TypeError, KeyError, IndexError):
            last_attempt = None
        if last_attempt is not None:
            last_exc = getattr(last_attempt, "exception", None)
            if isinstance(last_exc, BaseException):
                return last_exc
    cause: Any = getattr(instructor_exc, "__cause__", None)
    last_attempt = getattr(cause, "last_attempt", None)
    if last_attempt is not None:
        underlying = getattr(last_attempt, "_exception", None)
        if isinstance(underlying, BaseException):
            return underlying
    return None


def _parse_retry_after_seconds(value: Any) -> float | None:
    """Parse a ``Retry-After`` header value into a delay in seconds.

    The HTTP spec allows two forms: a non-negative number of seconds, or an
    HTTP-date. Numeric values are returned directly; HTTP-date values are
    converted to a delay relative to now, clamped to ``0.0`` when already past.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    if not isinstance(value, str):
        return None
    try:
        retry_date = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if retry_date.tzinfo is None:
        retry_date = retry_date.replace(tzinfo=UTC)
    delta_seconds = (retry_date - datetime.now(UTC)).total_seconds()
    return max(delta_seconds, 0.0)


def _provider_error_code_from_body(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    error_section = cast("dict[str, Any]", body).get("error")
    if not isinstance(error_section, dict):
        return None
    error_dict = cast("dict[str, Any]", error_section)
    code = error_dict.get("type") or error_dict.get("code")
    if isinstance(code, str):
        return code
    return None


def extract_openai_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill an OpenAI SDK exception into a ``ProviderErrorMetadata``.

    Tolerates the SDK's two exception shapes:

    - ``APIStatusError`` subclasses (``BadRequestError``, ``RateLimitError``,
      ``AuthenticationError`` …) expose ``status_code``, ``request_id``,
      ``response.headers`` (for ``Retry-After``), and ``body``. The SDK
      pre-unwraps ``body["error"]`` so ``body["type"]`` / ``body["code"]``
      sit at the top level — and are also mirrored to ``exc.type`` /
      ``exc.code`` as instance attributes.
    - ``APIConnectionError`` / ``APITimeoutError`` carry only a ``request``;
      every status-related field comes back as ``None``.
    """
    status_code = getattr(exc, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None
    request_id = getattr(exc, "request_id", None)
    if not isinstance(request_id, str):
        request_id = None
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    retry_after_seconds: float | None = None
    if headers is not None:
        retry_after_seconds = _parse_retry_after_seconds(headers.get("retry-after"))
    body = getattr(exc, "body", None)
    # OpenAI's _make_status_error pre-unwraps body["error"] onto exc.type / exc.code,
    # so we read those attributes directly rather than re-parsing the body.
    error_type = getattr(exc, "type", None)
    error_code = getattr(exc, "code", None)
    provider_error_code: str | None = None
    if isinstance(error_type, str):
        provider_error_code = error_type
    elif isinstance(error_code, str):
        provider_error_code = error_code
    return ProviderErrorMetadata(
        provider=ProviderName.OPENAI,
        sdk_exception_type=type(exc).__name__,
        message=str(exc),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=body,
    )


def extract_anthropic_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill an Anthropic SDK exception into a ``ProviderErrorMetadata``.

    Tolerates the two exception shapes in the Anthropic SDK:

    - ``APIStatusError`` subclasses expose ``status_code``, ``request_id``,
      ``response.headers`` (for ``Retry-After``) and ``body``.
    - ``APIConnectionError`` / ``APITimeoutError`` expose neither
      ``status_code`` nor ``response``; every status-related field comes back
      as ``None``.
    """
    status_code = getattr(exc, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None
    request_id = getattr(exc, "request_id", None)
    if not isinstance(request_id, str):
        request_id = None
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    retry_after_seconds: float | None = None
    if headers is not None:
        retry_after_seconds = _parse_retry_after_seconds(headers.get("retry-after"))
    body = getattr(exc, "body", None)
    return ProviderErrorMetadata(
        provider=ProviderName.ANTHROPIC,
        sdk_exception_type=type(exc).__name__,
        message=str(exc),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=_provider_error_code_from_body(body),
        body=body,
    )


def _provider_error_code_from_flat_body(body: Any) -> str | None:
    """Read ``type``/``code`` directly off the top-level body dict.

    Mistral returns flat error payloads (``{"message": ..., "type": ..., "code": ...}``)
    on most endpoints, in addition to the nested ``{"error": {...}}`` shape covered
    by ``_provider_error_code_from_body``.
    """
    if not isinstance(body, dict):
        return None
    flat = cast("dict[str, Any]", body)
    code = flat.get("type") or flat.get("code")
    if isinstance(code, str):
        return code
    return None


def _pipelex_service_error_code_from_body(body: Any) -> str | None:
    """Read the error code off a body a Pipelex-operated gateway rendered, preferring ``code``.

    Same traversal as ``_provider_error_code_from_body`` then
    ``_provider_error_code_from_flat_body`` — nested ``{"error": {…}}`` first, then
    the top level, which is where the vendored OpenAI client leaves it after
    pre-unwrapping — **but reading ``code`` before ``type``**, and that inversion
    is the whole point of the function.

    Our own services put the *specific* code in ``code`` and a generic
    OpenAI-shaped bucket in ``type``: every refusal on the native
    ``/v1/pipelex/*`` routes is rendered as
    ``{"error": {"message": …, "type": "invalid_request_error", "code":
    "pipelex_document_too_large"}}``. The vendor-facing precedence is right for
    Anthropic, whose error section carries a ``type`` and no ``code`` at all, and
    wrong here — it replaces every ``pipelex_*`` code with
    ``invalid_request_error`` and the code never reaches the classifier.

    The gateway's fail-closed shape carries only ``code`` (no ``type`` beside it),
    so the ``pig-0N`` family reads identically through either precedence.
    """
    if not isinstance(body, dict):
        return None
    body_dict = cast("dict[str, Any]", body)
    error_section = body_dict.get("error")
    sections: list[dict[str, Any]] = []
    if isinstance(error_section, dict):
        sections.append(cast("dict[str, Any]", error_section))
    sections.append(body_dict)
    for section in sections:
        code = section.get("code") or section.get("type")
        if isinstance(code, str):
            return code
    return None


def _parse_response_text_body(response: Any) -> tuple[Any | None, str | None]:
    """Read ``response.text`` and recover ``(body, provider_error_code)`` on a best-effort basis.

    Used by providers that deliver the response body as a *raw string* (Azure REST,
    FAL, HuggingFace, Mistral) — JSON-parse it when possible, fall back to the raw
    string for HTML / non-JSON bodies. The provider-error-code probe tries both the
    nested ``{"error": {...}}`` shape and the flat ``{"type": ..., "code": ...}``
    shape so the same helper works across providers.

    Returns ``(None, None)`` when the response has no text. Returns
    ``(raw_string, None)`` for non-JSON bodies. Returns ``(parsed_dict, code)``
    when the body parses as a JSON dict.
    """
    if response is None:
        return None, None
    try:
        raw_text = getattr(response, "text", None)
    except httpx.StreamError:
        # An httpx.Response whose body was never buffered (e.g. hub 1.x async
        # streaming errors) raises ResponseNotRead/StreamConsumed on ``.text``,
        # and the body cannot be recovered synchronously — treat as "no text".
        return None, None
    if not isinstance(raw_text, str) or not raw_text:
        return None, None
    try:
        parsed: Any = json.loads(raw_text)
    except (json.JSONDecodeError, ValueError):
        return raw_text, None
    if not isinstance(parsed, dict):
        return raw_text, None
    parsed_dict = cast("dict[str, Any]", parsed)
    code = _provider_error_code_from_body(parsed_dict) or _provider_error_code_from_flat_body(parsed_dict)
    return parsed_dict, code


def _google_provider_error_code_from_details(details: Any) -> str | None:
    """Read the symbolic ``status`` (e.g. ``RESOURCE_EXHAUSTED``) from a Google error payload.

    Google API error responses typically look like
    ``{"error": {"code": 429, "message": "...", "status": "RESOURCE_EXHAUSTED"}}``,
    but some endpoints flatten the same field to the top level. Try the nested
    shape first, then the top-level fallback.
    """
    if not isinstance(details, dict):
        return None
    details_dict = cast("dict[str, Any]", details)
    error_section = details_dict.get("error")
    if isinstance(error_section, dict):
        error_dict = cast("dict[str, Any]", error_section)
        nested_status = error_dict.get("status")
        if isinstance(nested_status, str):
            return nested_status
    top_status = details_dict.get("status")
    if isinstance(top_status, str):
        return top_status
    return None


def extract_google_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill a Google GenAI SDK exception into a ``ProviderErrorMetadata``.

    Google's exception shape differs from OpenAI/Anthropic:

    - ``APIError`` (and subclasses ``ClientError`` / ``ServerError``) expose
      ``code: int`` (the HTTP status code — *not* ``status_code``), ``message``,
      ``status`` (the symbolic name like ``RESOURCE_EXHAUSTED``), and
      ``details`` (the raw response JSON dict).
    - ``response`` may be ``None`` or any of ``httpx.Response`` /
      ``requests.Response`` / ``ReplayResponse``. We read ``x-goog-request-id``
      and ``retry-after`` from ``response.headers`` when present.
    """
    code = getattr(exc, "code", None)
    status_code = code if isinstance(code, int) else None
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    request_id: str | None = None
    retry_after_seconds: float | None = None
    if headers is not None:
        request_id_value = headers.get("x-goog-request-id") or headers.get("x-request-id")
        if isinstance(request_id_value, str):
            request_id = request_id_value
        retry_after_seconds = _parse_retry_after_seconds(headers.get("retry-after"))
    details = getattr(exc, "details", None)
    return ProviderErrorMetadata(
        provider=ProviderName.GOOGLE,
        sdk_exception_type=_resolve_sdk_exception_type(exc, status_code=status_code),
        message=str(exc),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=_google_provider_error_code_from_details(details),
        body=details,
    )


def extract_azure_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill an Azure REST API error (``httpx`` exception) into a ``ProviderErrorMetadata``.

    Azure REST returns errors as plain ``httpx`` exceptions — there is no SDK
    exception layer like Anthropic/OpenAI. We read fields off ``exc.response``
    when available (status code, headers, body) and JSON-parse the body on a
    best-effort basis. ``httpx.ConnectError`` / ``httpx.TimeoutException`` carry
    only a request; every status-related field comes back as ``None``.
    """
    return _build_azure_metadata(
        response=getattr(exc, "response", None),
        sdk_exception_type=type(exc).__name__,
        message=str(exc),
    )


def extract_azure_metadata_from_response(response: Any, *, sdk_exception_type: str, message: str) -> ProviderErrorMetadata:
    """Distill a *successful* Azure REST response into a ``ProviderErrorMetadata``.

    Used when the HTTP status was fine but the body failed to parse (malformed
    JSON): there is no ``httpx`` exception carrying the response, so the caller
    passes the ``httpx.Response`` directly along with the failure's type name
    and message.
    """
    return _build_azure_metadata(response=response, sdk_exception_type=sdk_exception_type, message=message)


def _build_azure_metadata(response: Any, *, sdk_exception_type: str, message: str) -> ProviderErrorMetadata:
    """Read status code, headers, and body off an Azure ``httpx.Response`` on a best-effort basis."""
    status_code = getattr(response, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None
    headers = getattr(response, "headers", None)
    request_id: str | None = None
    retry_after_seconds: float | None = None
    if headers is not None:
        request_id_value = headers.get("x-ms-request-id") or headers.get("apim-request-id") or headers.get("x-request-id")
        if isinstance(request_id_value, str):
            request_id = request_id_value
        retry_after_seconds = _parse_retry_after_seconds(headers.get("retry-after"))
    body, provider_error_code = _parse_response_text_body(response)
    return ProviderErrorMetadata(
        provider=ProviderName.AZURE,
        sdk_exception_type=sdk_exception_type,
        message=message,
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=body,
    )


def extract_fal_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill a FAL SDK exception into a ``ProviderErrorMetadata``.

    FAL's ``FalClientHTTPError`` carries ``status_code``, ``response_headers``
    (a plain dict), ``response`` (an httpx.Response), and ``error_type``
    (a SDK-level discriminator like ``ContentPolicyViolation``).
    ``FalClientTimeoutError`` / ``FalClientError`` / ``MissingCredentialsError``
    have no response metadata; every status field comes back as ``None``.
    """
    status_code = getattr(exc, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None
    response_headers = getattr(exc, "response_headers", None)
    request_id: str | None = None
    retry_after_seconds: float | None = None
    if response_headers is not None:
        request_id_value = response_headers.get("x-request-id") or response_headers.get("x-fal-request-id")
        if isinstance(request_id_value, str):
            request_id = request_id_value
        retry_after_seconds = _parse_retry_after_seconds(response_headers.get("retry-after"))
    error_type = getattr(exc, "error_type", None)
    base_provider_error_code: str | None = error_type if isinstance(error_type, str) else None
    response = getattr(exc, "response", None)
    body, parsed_provider_error_code = _parse_response_text_body(response)
    # Prefer the SDK's ``error_type`` attribute (FAL's canonical signal) over a
    # code recovered from the body.
    provider_error_code = base_provider_error_code or parsed_provider_error_code
    return ProviderErrorMetadata(
        provider=ProviderName.FAL,
        sdk_exception_type=type(exc).__name__,
        message=str(exc),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=body,
    )


def extract_huggingface_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill a HuggingFace ``HfHubHTTPError`` / ``InferenceTimeoutError`` into a ``ProviderErrorMetadata``.

    HuggingFace (hub 1.x) wraps an ``httpx.Response``; the ``request_id`` is
    mirrored onto ``exc.request_id`` by ``HfHubHTTPError.__init__`` (sourced from
    headers like ``X-Request-Id`` / ``X-Amzn-Trace-Id`` / ``X-Amz-Cf-Id``).
    Network-level failures (``InferenceTimeoutError``, raw ``httpx`` exceptions)
    carry no response metadata; every status field comes back as ``None``.
    """
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None
    request_id = getattr(exc, "request_id", None)
    if not isinstance(request_id, str):
        request_id = None
    headers = getattr(response, "headers", None)
    retry_after_seconds: float | None = None
    if headers is not None:
        retry_after_seconds = _parse_retry_after_seconds(headers.get("retry-after"))
    body, provider_error_code = _parse_response_text_body(response)
    return ProviderErrorMetadata(
        provider=ProviderName.HUGGINGFACE,
        sdk_exception_type=type(exc).__name__,
        message=str(exc),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=body,
    )


def extract_manifold_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill a raw-httpx failure against the Pipelex Manifold service into metadata.

    The manifold plugin's native routes (``/v1/pipelex/extract``, ``/v1/pipelex/search``) are not
    OpenAI-shaped, so they are called with plain ``httpx`` rather than through a vendor SDK. That
    leaves two exception shapes to distill:

    - ``httpx.HTTPStatusError``, which carries the whole ``response`` — status, headers, and a body
      this reads as JSON on a best-effort basis;
    - ``httpx.RequestError`` (connect, timeout, read), which carries only a request; every
      status-related field comes back as ``None``, and the class name is what the classify step
      matches on to call it a network failure.

    **The error code is read ``code`` first**, via ``_pipelex_service_error_code_from_body``, and
    the ordinary vendor-facing precedence would lose it here. A refusal these routes raise
    themselves is rendered as ``{"error": {"message": …, "type": "invalid_request_error", "code":
    "pipelex_document_too_large"}}`` — the generic bucket in ``type``, the frozen contract code the
    classifier actually needs in ``code`` — so reading ``type`` first replaces every ``pipelex_*``
    code with ``invalid_request_error``. The gateway's fail-closed ``pig-0N`` shape carries no
    ``type`` at all, so it reads the same either way.

    **It reports ``ProviderName.GATEWAY``**, and that is a decision rather than an oversight: the
    manifold service *is* the same gateway codebase, so it phrases quota exhaustion and rate
    limiting identically, and every ``match`` on ``ProviderName`` would need a second arm with the
    same body to say otherwise. Which of the two services answered is already carried by the error's
    model handle and backend name.
    """
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None
    headers = getattr(response, "headers", None)
    request_id: str | None = None
    retry_after_seconds: float | None = None
    if headers is not None:
        request_id_value = headers.get("x-request-id") or headers.get("x-portkey-trace-id")
        if isinstance(request_id_value, str):
            request_id = request_id_value
        retry_after_seconds = _parse_retry_after_seconds(headers.get("retry-after"))
    body: Any | None = None
    if response is not None:
        try:
            body = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            # A refusal the service did not render as JSON is still a refusal; the status code and
            # the message carry it, and insisting on a body here would trade a classified error for
            # a decode error raised while classifying one.
            body = None
    provider_error_code = _pipelex_service_error_code_from_body(body)
    return ProviderErrorMetadata(
        provider=ProviderName.GATEWAY,
        sdk_exception_type=type(exc).__name__,
        message=str(exc),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=body,
    )


def extract_gateway_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill a Portkey/Gateway SDK exception into a ``ProviderErrorMetadata``.

    ``APIStatusError`` subclasses expose ``status_code``, ``response`` (httpx) and
    ``body``. ``APIConnectionError`` / ``APITimeoutError`` carry only a request;
    every status field comes back as ``None``.

    **``body`` cannot be trusted to be the payload here**, and that is the whole
    reason for the response fallback below. Portkey's own
    ``_make_status_error_from_response`` sets ``body`` to
    ``json.loads(text)["error"]["message"]`` — the *message string*, not the
    document — so on every refusal the SDK itself raises there is no dict to read a
    code from. Reading ``exc.body`` alone recovered ``provider_error_code = None``
    for every Portkey-substrate error the runtime ever saw. A dict does reach here
    on the paths that bypass Portkey's factory (the vendored OpenAI client the
    image workers fall back to pre-unwraps ``body["error"]``), so the dict probe
    stays first and the response is only re-parsed when it came up empty.
    """
    status_code = getattr(exc, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    request_id: str | None = None
    retry_after_seconds: float | None = None
    if headers is not None:
        request_id_value = headers.get("x-request-id") or headers.get("x-portkey-trace-id")
        if isinstance(request_id_value, str):
            request_id = request_id_value
        retry_after_seconds = _parse_retry_after_seconds(headers.get("retry-after"))
    body: Any = getattr(exc, "body", None)
    provider_error_code = _pipelex_service_error_code_from_body(body)
    if provider_error_code is None:
        # The response is still buffered — the SDK just read ``.text`` off it to
        # build the message — so the payload it discarded is recoverable here
        # rather than lost. A recovered code means the helper parsed a document, so
        # it also replaces the stringified ``body`` and the in-process
        # content-policy scan gets structure back instead of one rendered sentence.
        recovered_body, _ = _parse_response_text_body(response)
        recovered_code = _pipelex_service_error_code_from_body(recovered_body)
        provider_error_code = recovered_code
        if recovered_code is not None:
            body = recovered_body
    return ProviderErrorMetadata(
        provider=ProviderName.GATEWAY,
        sdk_exception_type=type(exc).__name__,
        message=str(exc),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=body,
    )


def extract_mistral_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill a Mistral SDK exception into a ``ProviderErrorMetadata``.

    Tolerates the two shapes the Mistral SDK raises:

    - ``MistralError`` (and subclasses like ``SDKError``) carry ``status_code``,
      ``headers`` (httpx.Headers), and ``body`` as a *raw response text string*
      — not a pre-parsed dict like OpenAI/Anthropic. We JSON-parse it on a
      best-effort basis to recover ``provider_error_code`` from either the
      top-level ``type``/``code`` or the nested ``error.type``/``error.code``.
    - ``NoResponseError`` is a separate ``Exception`` subclass with no response
      metadata; every status-related field comes back as ``None``.
    """
    status_code = getattr(exc, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None
    headers = getattr(exc, "headers", None)
    request_id: str | None = None
    retry_after_seconds: float | None = None
    if headers is not None:
        request_id_value = headers.get("x-request-id")
        if isinstance(request_id_value, str):
            request_id = request_id_value
        retry_after_seconds = _parse_retry_after_seconds(headers.get("retry-after"))
    raw_body = getattr(exc, "body", None)
    body: Any = raw_body
    provider_error_code: str | None = None
    if isinstance(raw_body, str) and raw_body:
        try:
            parsed: Any = json.loads(raw_body)
        except (json.JSONDecodeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            parsed_dict = cast("dict[str, Any]", parsed)
            body = parsed_dict
            provider_error_code = _provider_error_code_from_flat_body(parsed_dict) or _provider_error_code_from_body(parsed_dict)
    return ProviderErrorMetadata(
        provider=ProviderName.MISTRAL,
        sdk_exception_type=_resolve_sdk_exception_type(exc, status_code=status_code),
        message=str(exc),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=body,
    )


# AWS Bedrock surfaces its canonical error signal as a code string; a
# hand-built ``ClientError`` (and some botocore paths) may carry no HTTP status.
# This maps the documented Bedrock error codes to an HTTP status so the
# provider-blind Classify step can treat Bedrock uniformly. Used only as a
# fallback when ``ResponseMetadata.HTTPStatusCode`` is absent.
_AWS_ERROR_CODE_TO_STATUS: dict[str, int] = {
    "ThrottlingException": 429,
    "ServiceQuotaExceededException": 400,
    "AccessDeniedException": 403,
    "UnauthorizedException": 401,
    "ValidationException": 400,
    "ModelNotReadyException": 429,
    "ServiceUnavailableException": 503,
    "InternalServerException": 500,
    "ResourceNotFoundException": 404,
    "ModelNotFoundException": 404,
}


def extract_bedrock_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill an AWS Bedrock ``botocore.exceptions.ClientError`` into a ``ProviderErrorMetadata``.

    botocore exposes a single ``response`` dict shaped like
    ``{"Error": {"Code": ..., "Message": ...}, "ResponseMetadata":
    {"RequestId": ..., "HTTPStatusCode": ..., "HTTPHeaders": {...}}}``.
    The ``provider_error_code`` we surface is the AWS error code (e.g.
    ``ThrottlingException``); the JSON ``body`` we keep is the full
    ``response`` dict so downstream consumers can recover the original
    error message and any extra fields without scraping ``str(exc)``.
    """
    response = getattr(exc, "response", None)
    response_dict = cast("dict[str, Any]", response) if isinstance(response, dict) else None
    error_section: dict[str, Any] = {}
    response_metadata: dict[str, Any] = {}
    if response_dict is not None:
        raw_error = response_dict.get("Error")
        if isinstance(raw_error, dict):
            error_section = cast("dict[str, Any]", raw_error)
        raw_meta = response_dict.get("ResponseMetadata")
        if isinstance(raw_meta, dict):
            response_metadata = cast("dict[str, Any]", raw_meta)
    status_code_value = response_metadata.get("HTTPStatusCode")
    status_code = status_code_value if isinstance(status_code_value, int) else None
    request_id_value = response_metadata.get("RequestId")
    request_id = request_id_value if isinstance(request_id_value, str) else None
    headers = response_metadata.get("HTTPHeaders")
    retry_after_seconds: float | None = None
    if isinstance(headers, dict):
        # botocore lowercases all HTTPHeaders keys, so ``retry-after`` is the canonical lookup.
        retry_after_seconds = _parse_retry_after_seconds(cast("dict[str, Any]", headers).get("retry-after"))
    error_code = error_section.get("Code")
    provider_error_code = error_code if isinstance(error_code, str) else None
    if status_code is None and provider_error_code is not None:
        status_code = _AWS_ERROR_CODE_TO_STATUS.get(provider_error_code)
    return ProviderErrorMetadata(
        provider=ProviderName.BEDROCK,
        sdk_exception_type=type(exc).__name__,
        message=str(exc),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=response_dict,
    )


def extract_linkup_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill a Linkup SDK exception into a ``ProviderErrorMetadata``.

    The Linkup Python SDK raises typed exceptions (``LinkupAuthenticationError``,
    ``LinkupTooManyRequestsError``, ``LinkupInvalidRequestError`` …) that wrap
    a plain message string but do not carry the underlying HTTP ``response``,
    ``status_code``, ``request_id``, or ``retry-after`` header. Every
    status-related field comes back as ``None``; the SDK class name is the
    main discriminator. We expose the exception class name as
    ``provider_error_code`` so downstream consumers can branch on it without
    importing the Linkup SDK at the call site.
    """
    return ProviderErrorMetadata(
        provider=ProviderName.LINKUP,
        sdk_exception_type=type(exc).__name__,
        message=str(exc),
        status_code=None,
        request_id=None,
        retry_after_seconds=None,
        provider_error_code=type(exc).__name__,
        body=None,
    )


_LOCAL_EXTRACT_TYPE_HIERARCHY: tuple[tuple[type[BaseException], str], ...] = (
    # ``FileNotFoundError`` is itself an ``OSError`` subclass, so it must be probed
    # first; otherwise a missing file would normalize to ``OSError`` → TRANSIENT
    # instead of CONTENT.
    (FileNotFoundError, "FileNotFoundError"),
    (ValueError, "ValueError"),
    (RuntimeError, "RuntimeError"),
    (OSError, "OSError"),
)


def extract_local_extract_metadata(exc: BaseException, *, provider: ProviderName) -> ProviderErrorMetadata:
    """Distill a local (non-HTTP) extraction exception into a ``ProviderErrorMetadata``.

    Local extractors (``docling``, ``pypdfium2`` …) run in-process against the
    file system; there is no HTTP response, no request id, no retry-after.
    The only meaningful signal is the underlying exception class
    (``FileNotFoundError``, ``ValueError``, ``RuntimeError``, ``OSError``),
    which we expose as ``sdk_exception_type``. The classifier matches on exact
    type names, so we normalize ``sdk_exception_type`` to the recognized ancestor
    here — a ``PermissionError`` from docling becomes ``"OSError"`` and routes to
    TRANSIENT instead of falling through to UNKNOWN. The original subclass name
    is preserved in ``provider_error_code`` for traceability.
    """
    raw_type_name = type(exc).__name__
    normalized_type_name = raw_type_name
    for ancestor_cls, ancestor_name in _LOCAL_EXTRACT_TYPE_HIERARCHY:
        if isinstance(exc, ancestor_cls):
            normalized_type_name = ancestor_name
            break
    return ProviderErrorMetadata(
        provider=provider,
        sdk_exception_type=normalized_type_name,
        message=str(exc),
        status_code=None,
        request_id=None,
        retry_after_seconds=None,
        provider_error_code=raw_type_name,
        body=None,
    )
