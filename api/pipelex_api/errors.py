"""API-authored error helpers — RFC 7807 problem responses for the 4xx/5xx the API owns.

These cover failures the API detects at its own boundary — request validation,
auth, payload-size limits, server misconfiguration — as opposed to pipelex
domain errors, which carry an `ErrorReport` and are translated by the global
`PipelexError` handler in `pipelex_api.exception_handlers`.

Each helper builds an RFC 7807 problem document (`build_problem_document_from_api_error`)
and raises `ApiError`. The `handle_api_error` handler registered in
`pipelex_api.exception_handlers` renders it as `application/problem+json`. Routes do
NOT catch pipelex exceptions themselves — anything that is not an
API-authored `ApiError` propagates to the global handlers. There are no
catch tuples here anymore: the global `PipelexError` / `Exception` handlers
are the single translation point for everything the API does not author
itself.
"""

from collections.abc import Mapping
from typing import Any, NamedTuple, NoReturn

from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.errors.error_codes import ErrorCode
from pipelex.errors.security_event import log_security_event, security_target_kind
from pipelex.errors.security_target import SecurityTargetClass

from pipelex_api.error_types import ErrorType
from pipelex_api.problem_document import build_problem_document_from_api_error


class ApiSecurityRefusal(NamedTuple):
    """The refusal of a security rule an API-authored error answers, which its handler logs as a security event.

    It holds what the event names and never what was refused: the refusal's code, the class of the error that refused
    (or the response's `error_type` when no error class did), and the class of destination when the rule knows it.
    """

    code: ErrorCode
    error_type: str
    target_class: SecurityTargetClass | None = None


def security_refusal_of(*, error: BaseException | None) -> ApiSecurityRefusal | None:
    """The security refusal `error` reports, when it is a `PipelexError` whose code is a security refusal, else `None`.

    For a route that answers a pipelex refusal with an API-authored problem document, which keeps the response the
    API has always given while the refusal still logs its security event.
    """
    if not isinstance(error, PipelexError):
        return None
    code = error.resolve_error_code()
    if security_target_kind(code=code) is None:
        return None
    return ApiSecurityRefusal(code=code, error_type=type(error).__name__, target_class=error.security_target_class)


class ApiError(Exception):
    """An API-authored error carrying a ready-rendered RFC 7807 problem document.

    Raised by the `raise_*` helpers below; rendered by `handle_api_error` in
    `pipelex_api.exception_handlers` as `application/problem+json`. Distinct from a pipelex
    `PipelexError`: there is no `ErrorReport` behind it — the failure is the
    API's own request validation, auth, or configuration check. The problem
    document is built at raise time, less the request context: `instance` and
    `request_id` are stamped by the handler, which is the frame that holds the
    `Request`.
    """

    def __init__(
        self,
        *,
        status_code: int,
        document: dict[str, Any],
        headers: dict[str, str] | None = None,
        security_refusal: ApiSecurityRefusal | None = None,
    ) -> None:
        self.status_code = status_code
        self.document = document
        self.headers: dict[str, str] = headers or {}
        self.security_refusal = security_refusal
        super().__init__(str(document.get("detail", "")))


def log_api_security_event(*, api_error: ApiError, extras: Mapping[str, str] | None) -> None:
    """Log the security event of an API-authored error that answers a security rule's refusal, and nothing otherwise.

    The event names the request through the log context and the run's extras the body carried, never a run id, since
    no run exists yet, and never what was refused.
    """
    refusal = api_error.security_refusal
    if refusal is None:
        return
    log_security_event(code=refusal.code, error_type=refusal.error_type, target_class=refusal.target_class, extras=extras)


def _raise_api_error(
    *,
    error_type: ErrorType,
    message: str,
    status: int,
    error_domain: ErrorDomain,
    headers: dict[str, str] | None = None,
    members: Mapping[str, Any] | None = None,
    security_refusal: ApiSecurityRefusal | None = None,
) -> NoReturn:
    """Build the RFC 7807 document and raise `ApiError`.

    The document is built without the request context: `instance` and
    `request_id` are stamped by `handle_api_error`, from the `Request` it is
    handed. That keeps these helpers parameter-clean — a call site deep inside
    a route still needs no `Request` — while leaving the API with no ambient
    request state of its own, and it is how the three error paths end up
    reading the route and the id from exactly one place.
    """
    document = build_problem_document_from_api_error(
        error_type,
        message,
        status,
        instance=None,
        request_id=None,
        error_domain=error_domain,
    )
    if members:
        # Extension members of RFC 7807 (section 3.2), such as `missing_blobs`: data a client acts on, beside the prose.
        document.update(members)
    raise ApiError(status_code=status, document=document, headers=headers, security_refusal=security_refusal)


def raise_validation_error(
    message: str,
    error_type: ErrorType = ErrorType.VALIDATION_ERROR,
    *,
    security_refusal: ApiSecurityRefusal | None = None,
) -> NoReturn:
    """Raise a 422 RFC 7807 problem response for invalid caller input.

    `security_refusal` names the security rule the input broke, when it broke one, so the response's handler logs
    the security event of the refusal; the response is the same either way.
    """
    _raise_api_error(error_type=error_type, message=message, status=422, error_domain=ErrorDomain.INPUT, security_refusal=security_refusal)


def raise_validation_problem(
    *,
    message: str,
    error_type: ErrorType,
    members: Mapping[str, Any],
    security_refusal: ApiSecurityRefusal | None = None,
) -> NoReturn:
    """Raise a 422 RFC 7807 problem response for invalid caller input, carrying extension members a client acts on.

    The members join the document beside `detail`, such as the `missing_blobs` a sender uploads before it sends the
    request again, or the `tree_refusal` naming the standard's refusal code and the paths it names. `security_refusal`
    is `raise_validation_error`'s.
    """
    _raise_api_error(
        error_type=error_type,
        message=message,
        status=422,
        error_domain=ErrorDomain.INPUT,
        members=members,
        security_refusal=security_refusal,
    )


def raise_bad_request(message: str, error_type: ErrorType = ErrorType.BAD_REQUEST) -> NoReturn:
    """Raise a 400 RFC 7807 problem response for a malformed request."""
    _raise_api_error(error_type=error_type, message=message, status=400, error_domain=ErrorDomain.INPUT)


def raise_payload_too_large(message: str) -> NoReturn:
    """Raise a 413 RFC 7807 problem response for an over-limit payload."""
    _raise_api_error(error_type=ErrorType.PAYLOAD_TOO_LARGE, message=message, status=413, error_domain=ErrorDomain.INPUT)


def raise_forbidden(message: str, error_type: ErrorType = ErrorType.FORBIDDEN) -> NoReturn:
    """Raise a 403 RFC 7807 problem response for an authorization failure."""
    _raise_api_error(error_type=error_type, message=message, status=403, error_domain=ErrorDomain.INPUT)


def raise_unauthenticated(message: str, error_type: ErrorType = ErrorType.UNAUTHENTICATED) -> NoReturn:
    """Raise a 401 RFC 7807 problem response, with the `WWW-Authenticate: Bearer` challenge.

    RFC 7807 fully supports the challenge header: moving the body to
    `application/problem+json` does not break an OAuth/JWT client that parses
    `WWW-Authenticate`.
    """
    _raise_api_error(
        error_type=error_type,
        message=message,
        status=401,
        error_domain=ErrorDomain.INPUT,
        headers={"WWW-Authenticate": "Bearer"},
    )


def raise_not_implemented(message: str, error_type: ErrorType) -> NoReturn:
    """Raise a 501 RFC 7807 problem response for a spec'd capability this server does not implement yet.

    For request shapes the published contract accepts but this deployment cannot serve (e.g. a
    `method_ref` closure selector before the method registry exists). A no-verdict condition —
    distinct from a 422 (the request is well-formed per the contract) and from a 200 invalid
    verdict (nothing was diagnosed). Classified `CONFIG` domain: neither the request nor the
    content is at fault.
    """
    _raise_api_error(error_type=error_type, message=message, status=501, error_domain=ErrorDomain.CONFIG)


def raise_internal_server_error(message: str, error_type: ErrorType) -> NoReturn:
    """Raise a 500 RFC 7807 problem response for an API-owned server fault.

    For the API's own configuration / invariant failures — a missing secret, a
    storage backend that cannot presign, absent package metadata. NOT for
    pipelex domain errors, which carry an `ErrorReport` and are handled by the
    global `PipelexError` handler. Classified `CONFIG` domain: an operator, not
    the caller, fixes it.
    """
    _raise_api_error(error_type=error_type, message=message, status=500, error_domain=ErrorDomain.CONFIG)
