"""Problem-document construction for the API's own errors.

A pure module — no FastAPI imports, no I/O. A pipelex error answers its own
problem document (`PipelexError.to_problem`, rendered by
`pipelex_api.exception_handlers.problem_response`); this module builds the
document of an API-authored 4xx/5xx that has no `PipelexError` behind it
(`raise_validation_error` and friends in `pipelex_api.errors`), from the static
`ErrorType` enum. It returns a plain `dict` the caller serializes as
`application/problem+json`.
"""

from typing import Any

from pipelex.base_exceptions import ErrorDomain

from pipelex_api.error_types import ErrorType
from pipelex_api.error_uri import error_type_title, error_type_uri

# Content type for every error response — RFC 7807 problem documents. Lives
# here, the module that builds them, so the FastAPI app, the middleware, and
# the error handlers can all reference one constant without a circular import.
PROBLEM_JSON_MEDIA_TYPE = "application/problem+json"


def build_problem_document_from_api_error(
    error_type: ErrorType,
    message: str,
    status: int,
    *,
    instance: str | None,
    request_id: str | None,
    error_domain: ErrorDomain | None = ErrorDomain.INPUT,
    retryable: bool = False,
) -> dict[str, Any]:
    """Build an RFC 7807 problem document for an API-authored error.

    Used by the `pipelex_api.errors` 4xx/5xx helpers, whose failures are the API's own
    request validation, auth, or configuration checks rather than a pipelex
    domain error — there is no `PipelexError` whose problem it could answer. The
    `type` URI and `title` are derived from the static `ErrorType` enum, and the
    `error_type` / `error_domain` / `retryable` members classify it until every
    API-authored error answers a registry code.

    `error_domain` defaults to `INPUT` — the caller can fix a 4xx. API-owned
    5xx (a missing secret, a misconfigured backend) pass `CONFIG`: an operator,
    not the caller, fixes those. `None` omits the member entirely, matching how
    a domain-less pipelex error renders.

    `retryable` defaults to `False`: every error this builder authors is a
    caller-input mistake or a server misconfiguration, neither of which a blind
    retry fixes. Carried as a positional contract member rather than dropped on
    `None`, so clients can drive retry logic uniformly without branching on
    field presence.

    `None`-valued context (`instance`, `request_id`) is dropped rather than
    emitted as `null`, as a problem document never writes a member as `null`.
    """
    document: dict[str, Any] = {
        "type": error_type_uri(error_type),
        "title": error_type_title(error_type),
        "status": status,
        "detail": message,
    }
    if instance is not None:
        document["instance"] = instance
    if request_id is not None:
        document["request_id"] = request_id
    document["error_type"] = error_type
    if error_domain is not None:
        document["error_domain"] = error_domain
    document["retryable"] = retryable
    return document


def with_request_context(document: dict[str, Any], *, instance: str | None, request_id: str | None) -> dict[str, Any]:
    """Return a copy of a problem document carrying the two request-scoped members.

    The `pipelex_api.errors` helpers build their document where no `Request` is in hand — a validation
    check deep inside a route, an auth refusal — so `instance` and `request_id` are stamped later,
    by the handler that renders the response and does hold the request. A copy rather than an
    in-place edit, because the `ApiError` a caller catches and inspects must read exactly as it was
    raised. `None` is dropped rather than emitted as `null`, the rule every builder here follows.
    """
    stamped = dict(document)
    if instance is not None:
        stamped["instance"] = instance
    if request_id is not None:
        stamped["request_id"] = request_id
    return stamped
