"""API-authored error helpers — RFC 7807 problem responses for the 4xx/5xx the API owns.

These cover failures the API detects at its own boundary — request validation,
auth, payload-size limits, server misconfiguration — as opposed to pipelex
domain errors, which carry an `ErrorReport` and are translated by the global
`PipelexError` handler in `api.exception_handlers`.

Each helper builds an RFC 7807 problem document (`build_problem_document_from_api_error`)
and raises `ApiError`. The `handle_api_error` handler registered in
`api.exception_handlers` renders it as `application/problem+json`. Routes do
NOT catch pipelex exceptions themselves — anything that is not an
API-authored `ApiError` propagates to the global handlers. There are no
catch tuples here anymore: the global `PipelexError` / `Exception` handlers
are the single translation point for everything the API does not author
itself.
"""

from typing import Any, NoReturn

from pipelex.base_exceptions import ErrorDomain

from api.error_types import ErrorType
from api.problem_document import build_problem_document_from_api_error


class ApiError(Exception):
    """An API-authored error carrying a ready-rendered RFC 7807 problem document.

    Raised by the `raise_*` helpers below; rendered by `handle_api_error` in
    `api.exception_handlers` as `application/problem+json`. Distinct from a pipelex
    `PipelexError`: there is no `ErrorReport` behind it — the failure is the
    API's own request validation, auth, or configuration check. The problem
    document is built at raise time, less the request context: `instance` and
    `request_id` are stamped by the handler, which is the frame that holds the
    `Request`.
    """

    def __init__(self, *, status_code: int, document: dict[str, Any], headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.document = document
        self.headers: dict[str, str] = headers or {}
        super().__init__(str(document.get("detail", "")))


def _raise_api_error(
    *,
    error_type: ErrorType,
    message: str,
    status: int,
    error_domain: ErrorDomain,
    headers: dict[str, str] | None = None,
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
    raise ApiError(status_code=status, document=document, headers=headers)


def raise_validation_error(message: str, error_type: ErrorType = ErrorType.VALIDATION_ERROR) -> NoReturn:
    """Raise a 422 RFC 7807 problem response for invalid caller input."""
    _raise_api_error(error_type=error_type, message=message, status=422, error_domain=ErrorDomain.INPUT)


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
