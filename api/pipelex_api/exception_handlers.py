"""Global FastAPI exception handlers that translate any failure into RFC 9457.

The single place the API renders a failure into an HTTP response. Every
handler produces the same `application/problem+json` shape: an `ApiError`
(raised by the `pipelex_api.errors` 4xx/5xx helpers) carries a pre-built problem
document; a FastAPI `RequestValidationError` from automatic request
validation is rendered into one; every `PipelexError` becomes its problem
document (`PipelexError.to_problem`); each orchestrator plugin's
transport-fault mapper (contributed through the plugin SPI's
`add_http_error_mapper`, discovered at app construction) gets its own handler
rendering the problem of the `PipelexError` it maps the fault to; everything
else becomes the problem of a `runtime.unexpected` failure, a 500. The base
names no orchestrator and imports no orchestrator SDK — the Temporal transport
classification is owned by the `pipelex-temporal` plugin and reaches us only as
a mapper. Routes therefore never catch and shape errors themselves.

**The reader picks the view.** A problem is built in the operator's view, and
the response carries the view of whoever made the request
(`pipelex_api.problem_view`): the operator view, with `diagnostics`, for a
request the authentication marked as the operator's, and the caller view,
without it, for anyone else. The HTTP status is the problem's code's, from the
error registry, and the operator's record of the failure, the log line, is
built from the operator view whichever view the response carries.

This module is deliberately import-side-effect-free — no env var reads, no
app construction. Keeping the handlers in their own module lets
tests import `register_exception_handlers` without dragging in the
production app's startup chain (`Pipelex.make`, `get_auth_dependency`,
router wiring), so a misconfigured env var can't crash test collection of
every module that imports a handler at once.
"""

import math
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, cast

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pipelex import log
from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.cogt.exceptions import find_inference_error_category_in_chain
from pipelex.errors.error_codes import error_code_spec, parse_error_code
from pipelex.errors.problem import PipelexProblem, ProblemView, caller_view_of
from pipelex.pipe_run.located_failure import make_unexpected_failure
from pipelex.plugins.registrar import HttpErrorMapperFn
from pipelex.system.telemetry.otel_constants import OTelLogAttr
from pipelex.tools.log.error_fields import ERROR_TYPE_FIELD
from starlette.requests import ClientDisconnect

from pipelex_api.error_types import ErrorType
from pipelex_api.errors import ApiError
from pipelex_api.middleware import request_id_of
from pipelex_api.problem_document import (
    PROBLEM_JSON_MEDIA_TYPE,
    build_problem_document_from_api_error,
    with_request_context,
)
from pipelex_api.problem_view import problem_view_of

if TYPE_CHECKING:
    from pipelex_api.security import RequestUser

# A Starlette/FastAPI async exception handler: `(request, exc) -> response`.
_ExceptionHandler = Callable[[Request, Exception], Awaitable[Response]]


def _user_id_of(request: Request) -> str | None:
    """Return the authenticated caller's id, when one is on the request.

    `pipelex_api.security._set_request_user` stores a `RequestUser` on
    `request.state.user` after a successful auth check (jwt, or
    `TRUST_FORWARDED_IDENTITY_HEADERS=true`). The global error-log sites read
    that here so an operator can tie a failure to a caller without grepping
    multiple log lines by `request_id` — and without each route having to log
    `user=<id>` itself before raising (which Phase 3 removed). Returns `None`
    pre-auth, on the static-API-key surface (no per-caller identity), or for
    `AUTH_MODE=none` without the forwarded-identity opt-in: `_emit_api_error`
    drops `None`-valued fields, so the attribute is absent from the record
    rather than carried as `user.id: null`.
    """
    user: RequestUser | None = getattr(request.state, "user", None)
    return user.user_id if user is not None else None


def _pipe_code_of(request: Request) -> str | None:
    """Return the body-derived `pipe_code` when `_parse_request` bound one.

    `pipelex_api.routes.pipelex.pipeline._parse_request` writes `pipe_code` onto
    `request.state` right after the body decodes (before
    `_validate_extras` / `from_body`), normalized through
    `_coerce_correlation_field` — empty / non-string / oversized inputs become
    `None`, so a caller cannot inflate every record the request emits. Returns
    `None` for routes that don't use `_parse_request`, for requests whose body
    never decoded (`_decode_body` raised 422), and for bodies that legitimately
    omitted `pipe_code` (the `mthds_contents`-only invocation).
    `_emit_api_error` drops `None`-valued fields.
    """
    return getattr(request.state, "pipe_code", None)


def _pipeline_run_id_of(request: Request) -> str | None:
    """Return the parsed `pipeline_run_id` when `_parse_request` bound one on the request.

    Same shape as `_pipe_code_of`. Source: the raw body's `pipeline_run_id` (the
    protocol wire field — the pipelex runtime internals keep calling it
    `pipeline_run_id`), normalized through `_coerce_correlation_field` at the
    binding site (empty string → `None`, oversized → truncated). Letting the
    field ride every error log lets an operator correlate the API-side failure
    with the worker-side traces that share the same run id, without each
    backend frame having to forward it.
    """
    return getattr(request.state, "pipeline_run_id", None)


def _request_fields(request: Request) -> dict[str, Any]:
    """Return the request-scoped attributes every error record carries.

    Single source of truth for the `url.path` / `user.id` / `pipe_code` /
    `pipeline_run_id` set, so the three log paths (`_log_error_report`,
    `_log_api_authored_error`, `handle_unexpected_error`) cannot drift. The
    path and the caller take their OpenTelemetry keys, the pipe and the run
    the runtime's own field names, so a query written for the runtime's lines
    finds these too.

    `request_id` is deliberately NOT here. `RequestIdMiddleware` binds it on the
    runtime's log context for the whole request, so it is already an attribute of
    every record emitted underneath — including the ones pipelex emits from inside
    a run, which this module never sees. Repeating it would give one value two
    sources. The path is here rather than on that context because the runtime
    reserves the context for its three run identifiers, and a URL path is not
    one of them; a field is the seam it offers for everything else.

    Each value is `None` when the corresponding state is not bound on this request;
    `_emit_api_error` drops those, so an unbound identifier is absent from the
    record rather than carried as `pipe_code: null`.
    """
    return {
        "url.path": request.url.path,
        OTelLogAttr.USER_ID: _user_id_of(request),
        "pipe_code": _pipe_code_of(request),
        "pipeline_run_id": _pipeline_run_id_of(request),
    }


# The HTTP status of a problem whose code the registry gives none, which only a client's own failure has.
_FALLBACK_PROBLEM_STATUS = 500


def _retry_after_header(problem: PipelexProblem, *, status: int) -> dict[str, str]:
    """Return a `Retry-After` header dict when a retry hint applies to this response.

    Emitted only when the response is itself a retry invitation — a 429, such as
    a provider's rate limit passed through — so a hint never rides a 500/422
    where `Retry-After` is meaningless. The problem's `retry_after`, which only a
    code inviting a retry carries and which is always finite, is rounded up to an
    integer. Empty dict when no hint applies.
    """
    if status != 429:
        return {}
    seconds = problem.retry_after
    if seconds is None or not math.isfinite(seconds):
        return {}
    return {"Retry-After": str(max(0, math.ceil(seconds)))}


def _status_of(problem: PipelexProblem) -> int:
    """The HTTP status of the response a problem is the body of: its code's, from the error registry."""
    code = parse_error_code(problem.code)
    if code is None:
        return _FALLBACK_PROBLEM_STATUS
    return error_code_spec(code).status or _FALLBACK_PROBLEM_STATUS


def _emit_api_error(*, fields: dict[str, Any], as_error: bool) -> None:
    """Emit one error record: a fixed message, everything about the failure a record attribute.

    The message is the same on every error line, whichever handler produced it, so it is the key a
    query or an alert selects this server's error stream by; there is no separate `event` field
    beside it. Nothing about the failure reaches the message, the status and the error type
    included: a log store groups and counts lines by their message, and `detail` is
    caller-controlled on several routes while the URL path is percent-decoded from the request
    line, so both ride fields, where a structured sink serializes them as values and a crafted
    newline stays inside one.

    The fields are handed to the runtime's log call as `fields=`, so each one becomes an attribute
    of the record and the selected sink decides how it goes on the wire — a key of its own on the
    JSON sink's line, an OTLP attribute on the collector's.

    `None`-valued fields are dropped, so an identifier this request never bound is
    absent rather than carried as a null. `as_error` picks the level — `error`
    (with the traceback) for operator-actionable failures, `warning` for
    `INPUT`-domain caller mistakes.
    """
    attributes = {key: value for key, value in fields.items() if value is not None}
    if as_error:
        log.error("A request ended in an error response", fields=attributes, include_exception=True)
    else:
        log.warning("A request ended in an error response", fields=attributes)


def _emit_at_error_level(status: int) -> bool:
    """Decide the log disposition from the final HTTP status, not the error domain.

    A 5xx is a server fault — log at `error` with a traceback. A 4xx is
    client-facing (a caller mistake or a benign conflict) — log at `warning`
    without a traceback. Keying off the status the code declares is what keeps
    a conflict, such as ``pipelex.run.already_exists`` answered with 409, out of
    the error dashboards, while still covering the 422 caller mistakes and the
    provider-429 passthrough without a second per-error-type registry.
    """
    return status >= 500


def _log_problem(problem: PipelexProblem, *, error: BaseException | None, request: Request, status: int) -> None:
    """Emit the structured error record for a failure answered with a problem, from the operator view.

    Disposition follows the HTTP status (see ``_emit_at_error_level``):
    a 4xx is client-facing and logs at `warning` without a traceback (caller
    mistakes, a provider's 429 passed through, and the 409 conflict), a 5xx
    logs at `error` with the traceback. `error.code` is the problem's code and
    `error.type` the class of the error it was built from, which only the
    operator view names. `user.id` rides every record when auth bound a caller —
    without it, the storage / pipeline-backend leg of a failure carries only
    `request_id` and `url.path`, and tying the failure to the caller requires
    correlating the request id across unrelated records.

    ``problem`` is the operator view, so the record carries the diagnostics
    whichever view the response carries. ``error`` is the exception the problem
    was built from, `None` for a failure a route received as a value, whose
    problem is all there is.
    """
    diagnostics = problem.diagnostics
    error_category = find_inference_error_category_in_chain(error) if error is not None else None
    error_class: str | None = None
    if diagnostics is not None:
        error_class = diagnostics.error_class
    elif error is not None:
        error_class = type(error).__name__
    fields: dict[str, Any] = {
        **_request_fields(request),
        "error.code": problem.code,
        ERROR_TYPE_FIELD: error_class,
        "error_category": error_category,
        "error_domain": ErrorDomain.from_problem_domain(problem.effective_domain),
        "retryable": problem.is_retryable,
        OTelLogAttr.HTTP_RESPONSE_STATUS_CODE: status,
        # The diagnostics' `provider` is the backend the error names, which a worker attributes its failure to, and their
        # `model` the handle the pipe named. The provider the SDK's metadata names, `openai` or `gateway`, is no backend's
        # name and no SDK's as the backends configuration names them, so it is left off: an unattributed failure has no
        # `backend_name` rather than a second spelling of the same backend.
        "backend_name": diagnostics.provider.name if diagnostics is not None and diagnostics.provider is not None else None,
        "model_handle": diagnostics.model if diagnostics is not None else None,
    }
    if diagnostics is not None and diagnostics.provider is not None:
        fields["provider_status_code"] = diagnostics.provider.status
        fields["provider_request_id"] = diagnostics.provider.request_id
    _emit_api_error(fields=fields, as_error=_emit_at_error_level(status))


def _log_api_authored_error(*, document: dict[str, Any], status: int, request: Request) -> None:
    """Emit the structured error record for an API-authored error response.

    Shares the disposition rule and the common-key set of `_log_problem`
    so every error response — a pipelex error's problem
    *or* an API-authored 4xx/5xx raised by an `pipelex_api.errors` helper — produces
    one error record a downstream sink can filter uniformly on its message and
    on `request_id`, `url.path`, `error.type`, `error_domain`, `retryable`
    and `http.response.status_code`. Without this, an API-owned 500 (a `raise_internal_server_error`
    site — `/version`'s missing-package case is the canonical example)
    would land with zero operator output, since `handle_api_error` only
    serializes the response.

    Where the two helpers differ — by design, matching what each side actually
    has to log:
    - API-authored docs add `detail`, which the API wrote itself from what it
      checked, so it is the cause an operator reads.
    - API-authored docs omit `error.code`, `error_category`, `backend_name`, `model_handle`,
      `provider_status_code` and `provider_request_id` — those are inference-domain classifiers pipelex
      sets only on classifiable failures and the API never authors itself.

    A 4xx logs at `warning` without a traceback; a 5xx logs at `error` with
    the traceback — same status-keyed disposition rule `_log_problem`
    uses (see ``_emit_at_error_level``), so a sink dedup'ing by level sees one
    shape.
    """
    fields: dict[str, Any] = {
        **_request_fields(request),
        ERROR_TYPE_FIELD: document.get("error_type"),
        "error_domain": document.get("error_domain"),
        "retryable": document.get("retryable"),
        OTelLogAttr.HTTP_RESPONSE_STATUS_CODE: status,
        "detail": document.get("detail"),
    }
    _emit_api_error(fields=fields, as_error=_emit_at_error_level(status))


def problem_response(problem: PipelexProblem, *, error: BaseException | None, request: Request) -> JSONResponse:
    """Render a problem built in the operator's view as the response to `request`, and log the failure.

    The single rendering of every failure a problem describes: a raised `PipelexError`, an
    orchestrator plugin's mapped transport fault, an unexpected exception, and a fault the
    `/validate` route receives as a value rather than a raise, for which `error` is `None`. The status is the code's, the
    record is logged from the operator view, and the body is the view of the request's reader
    (`pipelex_api.problem_view`), with its `status` member set to the response's.
    """
    status = _status_of(problem)
    _log_problem(problem, error=error, request=request, status=status)
    match problem_view_of(request):
        case ProblemView.OPERATOR:
            reader_problem = problem
        case ProblemView.CALLER:
            reader_problem = caller_view_of(problem=problem)
    document = reader_problem.model_copy(update={"status": status}).to_wire()
    return JSONResponse(
        status_code=status,
        content=document,
        media_type=PROBLEM_JSON_MEDIA_TYPE,
        headers=_retry_after_header(problem, status=status),
    )


def operator_problem_of(error: PipelexError, *, request: Request) -> PipelexProblem:
    """The problem of a `PipelexError` answered to `request`, in the operator's view, with the request's ids."""
    return error.to_problem(view=ProblemView.OPERATOR, request_id=request_id_of(request), pipeline_run_id=_pipeline_run_id_of(request))


async def handle_pipelex_error(request: Request, exc: Exception) -> Response:
    """Translate any pipelex `PipelexError` into its problem response.

    `to_problem` reports a located failure as its root fault at the pipe where
    it happened, so a wrapper exception still answers the code of the underlying
    failure. `exc` is typed `Exception` to match Starlette's handler contract;
    FastAPI only routes a `PipelexError` here, so the cast is sound. An
    orchestrator's workflow failure that is itself a `PipelexError` (e.g. the
    Temporal plugin's `WorkflowExecutionError`, which carries the problem its
    worker built) resolves here via Starlette's MRO walk; only a *bare*
    orchestrator-SDK transport error (no `PipelexError` in its MRO) is routed to
    that plugin's own mapper-backed handler instead.
    """
    error = cast("PipelexError", exc)
    return problem_response(operator_problem_of(error, request=request), error=error, request=request)


def _make_orchestrator_error_handler(mapper: HttpErrorMapperFn) -> "_ExceptionHandler":
    """Wrap one plugin-contributed error mapper into a FastAPI exception handler.

    The plugin owns the *classification* (it maps its bare transport/runtime
    exception — e.g. `temporalio.TemporalError` — to a `PipelexError` carrying the
    code the fault takes); core owns the *transport* exception type (resolved
    lazily by the registrar); the API owns the *presentation* (the same problem
    rendering every `PipelexError` gets via `problem_response`). This is what lets
    the base render an orchestrator's transport fault correctly while naming — and
    importing — no orchestrator SDK. `exc` is typed `Exception` to match
    Starlette's handler contract; FastAPI only routes the mapper's registered
    `exc_type` here.
    """

    async def _handler(request: Request, exc: Exception) -> Response:
        error = mapper(exc)
        return problem_response(operator_problem_of(error, request=request), error=error, request=request)

    return _handler


async def handle_unexpected_error(request: Request, exc: Exception) -> Response:
    """Catch-all for any failure matched by no more-specific handler.

    Covers anything that is not an `ApiError`, a `RequestValidationError`, a
    `PipelexError`, or an orchestrator plugin's mapped transport exception — so on
    the orchestrator-agnostic base (which installs no mapper), an *unmapped* bare
    transport/runtime error collapses here to a 500.

    One of the two `except Exception`-equivalent sites the project sanctions —
    the outermost handler of an API. The exception is stood in for by a
    `PipelexUnexpectedError` (`make_unexpected_failure`) and answered as its
    problem, `runtime.unexpected`, through the same rendering as every other
    failure: the caller reads the code's own sentences and never the exception's
    text, and the operator reads its class and message in `diagnostics`. A
    traceback reaches no response — it goes to the operator log, correlated by
    request id.

    This handler also covers a failure *inside* another handler: Starlette's
    `ServerErrorMiddleware` wraps the others, so such a failure still lands here
    rather than a bodyless default.
    """
    unexpected_failure = make_unexpected_failure(error=exc)
    return problem_response(operator_problem_of(unexpected_failure, request=request), error=exc, request=request)


async def handle_api_error(request: Request, exc: Exception) -> Response:
    """Render an API-authored `ApiError` as an RFC 7807 problem response.

    `ApiError` is raised by the `raise_*` helpers in `pipelex_api.errors` for the API's
    own 4xx/5xx — request validation, auth, payload limits, misconfiguration.
    The helper builds the problem document at raise time, where it holds no
    `Request`, so this handler stamps the two request-scoped members (`instance`
    and `request_id`) onto a copy of it — the same two values, read from the same
    place, as the pipelex-error and request-validation paths use. It then
    serializes that document, re-attaches any `WWW-Authenticate` challenge header,
    and emits the structured error record so an API-owned 500 from any
    route is observable (a `raise_internal_server_error` site like `version.py`'s
    missing-package case is the canonical example — it has no preceding
    `log.error` at the call site). `exc` is typed `Exception` to match Starlette's
    handler contract; FastAPI only routes an `ApiError` here, so the cast is sound.
    """
    api_error = cast("ApiError", exc)
    document = with_request_context(
        api_error.document,
        instance=request.url.path,
        request_id=request_id_of(request),
    )
    _log_api_authored_error(document=document, status=api_error.status_code, request=request)
    return JSONResponse(
        status_code=api_error.status_code,
        content=document,
        media_type=PROBLEM_JSON_MEDIA_TYPE,
        headers=api_error.headers,
    )


def _summarize_request_validation_error(exc: RequestValidationError) -> str:
    """Render FastAPI's per-field validation failures as one human-readable string.

    `RequestValidationError.errors()` is a list of per-field dicts; RFC 7807's
    `detail` is a single human-readable string, so each entry is rendered as
    `<location>: <message>` and the lot joined. Only `loc` and `msg` are read —
    both are plain strings / ints — so nothing unserializable from a crafted
    request body can reach the response.
    """
    parts: list[str] = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error.get("loc", ()))
        message = error.get("msg") or "Invalid input"
        parts.append(f"{location}: {message}" if location else message)
    return "; ".join(parts) or "Request validation failed"


# The `error_type` a FastAPI-validated body failing on exactly one of these fields carries,
# so a client branches on the same value whichever route refused the field. `/execute` and
# `/start` read their extras by hand and classify them the same way in `pipelex_api.routes.pipelex.pipeline`.
_BODY_FIELD_ERROR_TYPES: dict[str, ErrorType] = {
    "analytics_groups": ErrorType.INVALID_ANALYTICS_GROUPS,
}


def _request_validation_error_type(exc: RequestValidationError) -> ErrorType:
    """Classify a request validation failure by the body field that failed.

    Only a failure confined to one classified body field gets that field's type; anything
    else — several fields, a query parameter, a model-level validator — keeps the generic
    `ValidationError`, because naming one field would hide the others.
    """
    failed_fields: set[str] = set()
    for error in exc.errors():
        location = tuple(error.get("loc", ()))
        if len(location) < 2 or location[0] != "body":
            return ErrorType.VALIDATION_ERROR
        failed_fields.add(str(location[1]))
    if len(failed_fields) != 1:
        return ErrorType.VALIDATION_ERROR
    return _BODY_FIELD_ERROR_TYPES.get(failed_fields.pop(), ErrorType.VALIDATION_ERROR)


async def handle_request_validation_error(request: Request, exc: Exception) -> Response:
    """Translate FastAPI's automatic request validation failure into RFC 7807.

    FastAPI raises `RequestValidationError` when a request body, query, or path
    parameter fails the endpoint's declared Pydantic model — an extra field
    under `extra="forbid"`, a `min_length` / `max_length` breach, a missing or
    mistyped field, a `field_validator` raising `ValueError`, malformed JSON. Its
    built-in handler would answer with a bare `{"detail": [...]}` /
    `application/json` body; registering this handler overrides that so an
    endpoint's caller-input rejection is the same `application/problem+json`
    shape as an explicit `raise_validation_error` — one error contract across
    every endpoint. `exc` is typed `Exception` to match Starlette's handler
    contract; FastAPI only routes a `RequestValidationError` here, so the cast
    is sound.
    """
    validation_error = cast("RequestValidationError", exc)
    document = build_problem_document_from_api_error(
        _request_validation_error_type(validation_error),
        _summarize_request_validation_error(validation_error),
        422,
        instance=request.url.path,
        request_id=request_id_of(request),
        error_domain=ErrorDomain.INPUT,
    )
    # Same error record as an explicit `raise_validation_error`,
    # so FastAPI's automatic-validation 422s aren't silent in operator logs.
    _log_api_authored_error(document=document, status=422, request=request)
    return JSONResponse(status_code=422, content=document, media_type=PROBLEM_JSON_MEDIA_TYPE)


async def handle_client_disconnect(request: Request, exc: Exception) -> Response:  # noqa: ARG001 — Starlette's handler contract
    """Answer a client that left before its request body arrived in full with a 400, logged as a caller's failure.

    Starlette raises `ClientDisconnect` from a body read when the client goes away mid-upload: from the
    nesting check of a `JsonBodyRoute`, and from the run routes, which read their raw body themselves.
    Nobody is left to read the answer, so what matters is the record it leaves: a 400 `BadRequest` at
    `warning`, as FastAPI's own body read answered it, never a 500 server fault logged with a traceback.
    """
    document = build_problem_document_from_api_error(
        ErrorType.BAD_REQUEST,
        "The client disconnected before the request body was received in full.",
        400,
        instance=request.url.path,
        request_id=request_id_of(request),
        error_domain=ErrorDomain.INPUT,
    )
    _log_api_authored_error(document=document, status=400, request=request)
    return JSONResponse(status_code=400, content=document, media_type=PROBLEM_JSON_MEDIA_TYPE)


def register_exception_handlers(
    app: FastAPI,
    *,
    http_error_mappers: dict[type[Exception], HttpErrorMapperFn] | None = None,
) -> None:
    """Register the app-level exception handlers on `app`.

    Resolution is most-specific-first: an API-authored `ApiError` →
    `handle_api_error`; a FastAPI `RequestValidationError` (automatic
    request-body / parameter validation) → `handle_request_validation_error`; a
    Starlette `ClientDisconnect` (the client left mid-upload) →
    `handle_client_disconnect`; a
    `PipelexError` (including an orchestrator plugin's `PipelexError`-derived
    workflow failure) → `handle_pipelex_error`; a bare orchestrator-SDK transport
    error → that plugin's mapper-backed handler (see `http_error_mappers`);
    anything else → `handle_unexpected_error`. Registering `RequestValidationError`
    overrides FastAPI's built-in handler so its automatic-validation failures answer
    in the same `application/problem+json` shape as every other error, not the
    default `{"detail": [...]}`. Shared by the production app and by the unit
    tests, which register the same handlers on a throwaway app.

    `http_error_mappers` is the `{exc_type: to_pipelex_error}` map an orchestrator
    plugin contributes through the plugin SPI (`PluginRegistrar.add_http_error_mapper`,
    read back via `get_http_error_mappers`). The caller resolves it at app
    construction — `pipelex_api.main` builds the registrar and passes it; the base resolves
    an empty map (it installs no orchestrator plugin), so no transport handler is
    registered and the only fallback for an unclassified failure stays the catch-all
    500. Each entry registers one handler that runs the mapper and renders the
    resulting `PipelexError`'s problem through the shared rendering — so core
    and the API name no orchestrator SDK. Keeping the parameter explicit (rather than
    calling `build_registrar` in here) preserves this module's import-side-effect-free
    contract: tests register handlers on a throwaway app without a booted Pipelex, and
    a test contributes a synthetic mapper to prove the seam without installing a plugin.

    No handler takes a disclosure setting: the view of every problem response is
    picked per request, by the identity its authentication established
    (`pipelex_api.problem_view`).
    """
    app.add_exception_handler(ApiError, handle_api_error)
    app.add_exception_handler(RequestValidationError, handle_request_validation_error)
    app.add_exception_handler(ClientDisconnect, handle_client_disconnect)
    app.add_exception_handler(PipelexError, handle_pipelex_error)
    for exc_type, mapper in (http_error_mappers or {}).items():
        app.add_exception_handler(exc_type, _make_orchestrator_error_handler(mapper))
    app.add_exception_handler(Exception, handle_unexpected_error)
