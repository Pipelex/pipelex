"""The Pipelex service's own error codes, contributed to the runtime's service error vocabulary.

The service refuses some requests itself, before any provider sees them, under codes of its own:
the ``pig-0N`` family on the LLM routes and the frozen ``pipelex_*`` contract codes on the native
``/v1/pipelex/*`` routes. They group into three families by what the caller has to do — a
request-shape limit, a reference that cannot be resolved, a request that cannot be routed — and each
code becomes one ``ServiceErrorCode`` entry: its category, its action and its advice.
``PipelexHostedPlugin.register`` contributes ``PIPELEX_HOSTED_SERVICE_ERROR_CODES``, which the classifier then
consults ahead of the status ladder.

None of these is retryable: the service refused before a provider saw the request, and the identical
request earns the identical refusal.
"""

from enum import StrEnum

from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.cogt.inference.service_error_vocabulary import ServiceErrorCode


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
# the Anthropic worker that Claude travels on (reported as ``ANTHROPIC``) —
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
# identify the gateway (more than one SDK hop reaches it, under more than one provider name), while ``pig-``
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

    Each member corresponds to one of the gateway's own ``pig-`` codes, at HTTP
    400, which is the contract between the two repositories — the wording of a
    refusal is free to change, the code is not. The substrate's
    ``model_not_allowed_error`` is a routing refusal too, but the runtime
    classifies it itself, because Portkey's cloud answers it for a caller's own
    workspace as well (see ``MODEL_NOT_ALLOWED_ERROR_CODE`` in core).
    """

    #: ``pig-01`` at HTTP 400 — the request body names one that no integration
    #: this deployment carries lists. Reached from the runtime by a model deck
    #: whose handle the gateway does not serve: a stale deck, a typo in a
    #: ``.mthds`` file's model, or a model the deployment deliberately does not
    #: carry.
    #:
    #: **The code covers two other facts and does not distinguish them**: a body
    #: that names no model, and a body the gateway could not parse at all — its
    #: model reader returns "no model" from a bare ``catch`` around the JSON and
    #: multipart reads alike, so a truncated or non-conforming payload lands here
    #: too. Only the gateway's message says which, which is why the rendered
    #: advice defers to it rather than asserting a deck disagreement (see
    #: ``_routing_refusal_entry``). Splitting the code is a
    #: gateway-side change, filed for the hosted plane as L-260902-701614.
    UNKNOWN_MODEL = "unknown_model"
    #: ``pig-02`` at HTTP 400 — the model resolves, but to an integration the
    #: deployment has switched off because a credential variable is unset. Nothing
    #: about the request causes it and no request avoids it: the gateway's own
    #: message names the integration and the variables whoever operates it must
    #: set.
    DISABLED_INTEGRATION = "disabled_integration"
    #: ``pig-05`` at HTTP 400 — a native-protocol path names a model that another
    #: provider serves. Today that is only Google's generative shape —
    #: ``/v1/<v1|v1alpha|v1beta>/models/<model>:generateContent`` or its
    #: ``streamGenerateContent`` twin, under the gateway's own ``/v1`` prefix —
    #: the one ``nativeProtocolPaths.ts`` admits. Reaching it means the model deck and the
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
# Claude travels on the Anthropic worker — while ``pig-`` is the gateway's
# own code namespace and no vendor emits into it.
#
# **Two of the gateway's routing codes are deliberately absent**, and the omission
# is the scope decision rather than an oversight:
#
# - ``pig-03`` ("the client tried to route") refuses a ``x-portkey-*`` steering
#   header, the ``?model=`` query form, a ``@<slug>/<model>`` virtual-key model, or
#   a path and body naming different models. No client that talks to a
#   Pipelex-operated gateway today produces any of those, so reaching it means a
#   client bug rather than a caller's or an operator's mistake, and the status
#   ladder's reading is as good as any.
#
#   Two limits on that sentence, because it is the whole reason the code stays
#   out. ``tests/unit/pipelex/providers/pipelex_hosted/test_pipelex_hosted_clients.py`` pins
#   the hosted clients against the four steering headers by name, while the
#   gateway refuses on an *allow*-list — so a ``portkey_ai`` release that starts
#   sending some other ``x-portkey-*`` header turns every request into a
#   ``pig-03`` with that test still green. The hosted image path still travels
#   on ``portkey_ai``, which is the one client that could start doing so.
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


def _request_limit_entry(*, code: str, limit: GatewayRequestLimit) -> ServiceErrorCode:
    """The entry for a request-shape refusal.

    The advice deliberately says nothing about a number. The caps are the deployment's, they differ
    between deployments, and the gateway already names its own figures in the message this advice
    sits beside — repeating a compiled-in guess here is how advice starts contradicting the refusal it
    explains.
    """
    match limit:
        case GatewayRequestLimit.BODY_TOO_LARGE:
            # The caller sent more than the deployment serves — a smaller input is the whole remedy,
            # and it is theirs to make. The same holds for the two members below.
            return ServiceErrorCode(
                code=code,
                category=InferenceErrorCategory.CONTENT,
                user_action_kind=UserActionKind.CHANGE_INPUT,
                detail="The request was too large for the inference gateway — send less in one call, or use smaller inputs.",
            )
        case GatewayRequestLimit.OBJECT_TOO_LARGE:
            return ServiceErrorCode(
                code=code,
                category=InferenceErrorCategory.CONTENT,
                user_action_kind=UserActionKind.CHANGE_INPUT,
                detail="A file the request refers to is over the inference gateway's per-file size limit — use a smaller file.",
            )
        case GatewayRequestLimit.BODY_TOO_DEEP:
            return ServiceErrorCode(
                code=code,
                category=InferenceErrorCategory.CONTENT,
                user_action_kind=UserActionKind.CHANGE_INPUT,
                detail="The request nests too deeply for the inference gateway — flatten the inputs or the output structure.",
            )
        case GatewayRequestLimit.BODY_LENGTH_REQUIRED:
            # Nothing about the *content* is wrong here: an HTTP client framed the request in a way the
            # gateway will not bound. No client the runtime ships produces it, so reaching this means
            # something in the transport stack changed — which is an operator's problem, not the caller's.
            return ServiceErrorCode(
                code=code,
                category=InferenceErrorCategory.CONFIGURATION,
                user_action_kind=UserActionKind.CONTACT_SUPPORT,
                detail=(
                    "The inference gateway could not read the request's declared size and refused it: it requires a "
                    "Content-Length and does not accept a chunked body. Nothing about the inputs causes this — contact support."
                ),
            )


def _unresolved_reference_entry(*, code: str, reference: GatewayUnresolvedReference) -> ServiceErrorCode:
    """The entry for a reference the gateway could not resolve.

    The advice names no key, host, status or media type, for the same reason the request-limit advice
    names no number: the gateway's own refusal message sits beside it and already states the
    specifics. What the advice adds is what the caller should *do*, which the message does not say.

    Not retryable even for ``DOCUMENT_UNREACHABLE``, where the origin *could* have been transiently
    down: the gateway renders it a 400, a retry would re-run a whole inference call just to re-fetch a
    document, and the common case is a URL that is simply wrong.
    """
    match reference:
        case GatewayUnresolvedReference.STORAGE_NOT_SERVED:
            # This deployment serves no ``pipelex-storage://`` references at all, because no bucket is
            # configured for it. Nothing about the inputs causes it and no input can avoid it — it is an
            # operator's problem, like ``BODY_LENGTH_REQUIRED``.
            return ServiceErrorCode(
                code=code,
                category=InferenceErrorCategory.CONFIGURATION,
                user_action_kind=UserActionKind.CONTACT_SUPPORT,
                detail=_unresolved_reference_detail(reference=reference),
            )
        case (
            GatewayUnresolvedReference.REFERENCE_UNRESOLVED
            | GatewayUnresolvedReference.STORAGE_REFERENCE_INVALID
            | GatewayUnresolvedReference.STORAGE_OBJECT_UNREADABLE
            | GatewayUnresolvedReference.DOCUMENT_URL_REFUSED
            | GatewayUnresolvedReference.DOCUMENT_HOST_REFUSED
            | GatewayUnresolvedReference.DOCUMENT_UNREACHABLE
            | GatewayUnresolvedReference.DOCUMENT_CONTENT_UNUSABLE
        ):
            # The reference is the caller's to fix — a different key, a different URL, or the file
            # uploaded where the gateway can reach it. ``DOCUMENT_HOST_REFUSED`` belongs here too: the
            # refusal is a security policy rather than a fault, but the caller is still the one who can
            # act on it, and its advice is where that distinction is stated.
            return ServiceErrorCode(
                code=code,
                category=InferenceErrorCategory.CONTENT,
                user_action_kind=UserActionKind.CHANGE_INPUT,
                detail=_unresolved_reference_detail(reference=reference),
            )


def _unresolved_reference_detail(*, reference: GatewayUnresolvedReference) -> str:
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


def _routing_refusal_entry(*, code: str, refusal: GatewayRoutingRefusal) -> ServiceErrorCode:
    """The entry for a request the gateway refused to route.

    Every member is ``CONFIGURATION``: nothing in the prompt, the parameters or the inputs causes any
    of these, and no edit to them avoids one. Without the family they take the status ladder's 400
    arm and read as a provider rejecting the caller's content.

    The advice names no integration, protocol or capability: the gateway's own message sits beside it
    and already states every specific. Every member whose remedy could be a deck edit says "the model
    deck" out loud: the runtime picks the model, the protocol and the route from its own deck, so those
    refusals usually mean the deck and the gateway disagree about a model rather than that the caller
    chose badly.
    """
    match refusal:
        case GatewayRoutingRefusal.UNKNOWN_MODEL:
            # The deployment does not know that model at all — which is exactly what
            # ``is_model_not_found`` means, so this is the one member that sets it. It selects the
            # family's ``*ModelNotFoundError`` class, which ``pipe_operator.py`` re-raises as a
            # ``PipeOperatorModelAvailabilityError`` carrying the model handle.
            #
            # The advice's second sentence is hedged deliberately. ``pig-01`` is the gateway's answer
            # to three different facts — it serves no such model, the body named none, and the body
            # could not be parsed at all — and the wire code does not tell them apart. Only the
            # gateway's own message does, so the advice sends the reader there before it sends them to
            # the deck. Splitting the code is the real fix, filed for the hosted plane as
            # L-260902-701614.
            return ServiceErrorCode(
                code=code,
                category=InferenceErrorCategory.CONFIGURATION,
                user_action_kind=UserActionKind.CHANGE_MODEL,
                is_model_not_found=True,
                detail=(
                    "The inference gateway does not serve that model — pick a model this deployment serves. Its own message is "
                    "the authority on which: the same code also answers a request it could not read a model out of at all. "
                    "If it names a model your model deck lists, the deck and the gateway disagree about what is available."
                ),
            )
        case GatewayRoutingRefusal.DISABLED_INTEGRATION:
            # The integration is switched off because whoever operates the gateway never set its
            # credential. The deployment is what has to change, not the request — so this is the
            # family's ``CONTACT_SUPPORT`` arm. ``CHECK_CREDENTIALS`` would send a hosted caller to
            # rotate their own perfectly valid key; ``CHANGE_MODEL`` would send them shopping for a
            # model over an operator's unset variable. The handle resolved, so this is not a model the
            # deployment does not know.
            return ServiceErrorCode(
                code=code,
                category=InferenceErrorCategory.CONFIGURATION,
                user_action_kind=UserActionKind.CONTACT_SUPPORT,
                detail=(
                    "The model is served by an integration this inference gateway has not enabled — its credentials are unset. "
                    "Nothing about the request causes this, and none of your own credentials are at fault: the error message "
                    "names the integration and the variables whoever operates the gateway has to set. Contact support."
                ),
            )
        case GatewayRoutingRefusal.WRONG_PROTOCOL:
            # The model exists and is served, just not over the protocol that was spoken — so it is not
            # a model-not-found, and ``CHANGE_MODEL`` is still what an end caller can do about it.
            return ServiceErrorCode(
                code=code,
                category=InferenceErrorCategory.CONFIGURATION,
                user_action_kind=UserActionKind.CHANGE_MODEL,
                detail=(
                    "The inference gateway serves that model, but not over the protocol the request used for it — your model "
                    "deck names a different backend for it than the gateway routes it to. Correct the deck, or pick another model."
                ),
            )
        case GatewayRoutingRefusal.UNSERVED_CAPABILITY:
            # Same reading: the model exists and is served, it just cannot do what was asked.
            return ServiceErrorCode(
                code=code,
                category=InferenceErrorCategory.CONFIGURATION,
                user_action_kind=UserActionKind.CHANGE_MODEL,
                detail=(
                    "The model's integration does not serve that capability on the inference gateway — the error message names "
                    "the provider and what was asked of it. Pick a model whose provider serves it, or correct the model deck."
                ),
            )


# Every code the service emits on its own that the runtime reads, one entry each. The three families
# are disjoint by construction — a code names a bound the request exceeded, a reference that could not
# be resolved, or a request that could not be routed, never two of them — and the registrar refuses a
# code claimed twice, so a code added to two maps fails the boot rather than picking one silently.
PIPELEX_HOSTED_SERVICE_ERROR_CODES: tuple[ServiceErrorCode, ...] = (
    *(_request_limit_entry(code=code, limit=limit) for code, limit in _GATEWAY_REQUEST_LIMIT_BY_CODE.items()),
    *(_unresolved_reference_entry(code=code, reference=reference) for code, reference in _GATEWAY_UNRESOLVED_REFERENCE_BY_CODE.items()),
    *(_routing_refusal_entry(code=code, refusal=refusal) for code, refusal in _GATEWAY_ROUTING_REFUSAL_BY_CODE.items()),
)
