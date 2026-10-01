"""Global FastAPI exception handlers that translate any failure into RFC 7807.

The single place the API renders a failure into an HTTP response. Every
handler produces the same `application/problem+json` shape: an `ApiError`
(raised by the `pipelex_api.errors` 4xx/5xx helpers) carries a pre-built problem
document; a FastAPI `RequestValidationError` from automatic request
validation is rendered into one; every `PipelexError` is turned into a
problem document built from its `ErrorReport`; each orchestrator plugin's
transport-fault mapper (contributed through the plugin SPI's
`add_http_error_mapper`, discovered at app construction) gets its own handler
rendering the `ErrorReport` it produces; everything else collapses to a
catch-all 500 that discloses under VERBOSE and is sanitized under STRICT, like
every other response here. The base names no orchestrator and imports no orchestrator SDK
— the Temporal transport classification that used to live here is now owned by
the `pipelex-temporal` plugin and reaches us only as a mapper. Routes
therefore no longer need to catch and shape errors themselves.

This module is deliberately import-side-effect-free — no env var reads, no
app construction. `pipelex_api/main.py` calls `register_exception_handlers(app,
disclosure_mode=...)` at startup with the already-resolved disclosure mode
(its own fail-fast read is what keeps production strict on a bad
`ERROR_DISCLOSURE` value). Keeping the handlers in their own module lets
tests import `register_exception_handlers` without dragging in the
production app's startup chain (`Pipelex.make`, `get_auth_dependency`,
router wiring), so a misconfigured env var can't crash test collection of
every module that imports a handler at once.
"""

import math
from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING, Any, cast

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pipelex import log
from pipelex.base_exceptions import DisclosureMode, ErrorDomain, ErrorReport, PipelexError
from pipelex.plugins.registrar import HttpErrorMapperFn
from starlette.requests import ClientDisconnect

from pipelex_api.error_types import ErrorType
from pipelex_api.errors import ApiError
from pipelex_api.middleware import request_id_of
from pipelex_api.problem_document import (
    PROBLEM_JSON_MEDIA_TYPE,
    build_problem_document,
    build_problem_document_from_api_error,
    with_request_context,
)

if TYPE_CHECKING:
    from pipelex_api.security import RequestUser

# A Starlette/FastAPI async exception handler: `(request, exc) -> response`.
_ExceptionHandler = Callable[[Request, Exception], Awaitable[Response]]

# The value of the `event` field every error record carries: the one key a log sink filters this
# server's error stream on, whichever of the handlers below produced the record.
API_ERROR_EVENT = "api_error"


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
    rather than carried as `user_id: null`.
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

    Single source of truth for the `route` / `user_id` / `pipe_code` /
    `pipeline_run_id` set, so the three log paths (`_log_error_report`,
    `_log_api_authored_error`, `handle_unexpected_error`) cannot drift.

    `request_id` is deliberately NOT here. `RequestIdMiddleware` binds it on the
    runtime's log context for the whole request, so it is already an attribute of
    every record emitted underneath — including the ones pipelex emits from inside
    a run, which this module never sees. Repeating it would give one value two
    sources. `route` is here rather than on that context because the runtime
    reserves the context for its three run identifiers, and a route path is not
    one of them; a field is the seam it offers for everything else.

    Each value is `None` when the corresponding state is not bound on this request;
    `_emit_api_error` drops those, so an unbound identifier is absent from the
    record rather than carried as `pipe_code: null`.
    """
    return {
        "route": request.url.path,
        "user_id": _user_id_of(request),
        "pipe_code": _pipe_code_of(request),
        "pipeline_run_id": _pipeline_run_id_of(request),
    }


def _retry_after_header(report: ErrorReport) -> dict[str, str]:
    """Return a `Retry-After` header dict when a retry hint applies to this response.

    Emitted only when the response is itself a retry invitation — the
    provider-429 passthrough (`report.http_status == 429`) — so a hint never
    rides a 500/422 where `Retry-After` is meaningless. The provider's
    `retry_after_seconds` is rounded up and clamped to a non-negative integer;
    a non-finite value (a provider sending `Retry-After: inf` / `nan`) is
    dropped rather than crashing `math.ceil`. Empty dict when no usable hint
    applies.
    """
    if report.http_status != 429:
        return {}
    metadata = report.provider_metadata
    if metadata is None:
        return {}
    seconds = metadata.retry_after_seconds
    if seconds is None or not math.isfinite(seconds):
        return {}
    return {"Retry-After": str(max(0, math.ceil(seconds)))}


def _error_summary(attributes: Mapping[str, Any]) -> str:
    """Return the human-readable message an `api_error` record carries.

    Built from server-authored values only — the HTTP status and the error type,
    both of which the API or pipelex chose. Nothing a caller supplied ever reaches
    the message: `detail` is caller-controlled on several routes, and the route
    path is percent-decoded from the request line, so both ride fields instead,
    where a structured sink serializes them as values and a crafted newline stays
    inside one. The message says which failure it is; the fields say everything
    about it.
    """
    status = attributes.get("status")
    error_type = attributes.get("error_type")
    return f"API error {status}: {error_type}" if error_type else f"API error {status}"


def _emit_api_error(*, fields: dict[str, Any], as_error: bool) -> None:
    """Emit one `event=api_error` record: a summary message, everything else a record attribute.

    The fields are handed to the runtime's log call as `fields=`, so each one
    becomes an attribute of the record and the selected sink decides how it goes
    on the wire — a key of its own on the JSON sink's line, an OTLP attribute on
    the collector's. Nothing is flattened into the message here any more, which
    is what retires the API's own `key=value` rendering and its escaping with it.

    `None`-valued fields are dropped, so an identifier this request never bound is
    absent rather than carried as a null. `as_error` picks the level — `error`
    (with the traceback) for operator-actionable failures, `warning` for
    `INPUT`-domain caller mistakes.
    """
    attributes = {key: value for key, value in fields.items() if value is not None}
    summary = _error_summary(attributes)
    if as_error:
        log.error(summary, fields=attributes, include_exception=True)
    else:
        log.warning(summary, fields=attributes)


def _emit_at_error_level(status: int) -> bool:
    """Decide the log disposition from the final HTTP status, not the error domain.

    A 5xx is a server fault — log at `error` with a traceback. A 4xx is
    client-facing (a caller mistake or a benign conflict) — log at `warning`
    without a traceback. Keying off the post-override status (see
    ``_ERROR_TYPE_STATUS_OVERRIDES``) is what keeps an API-level 4xx override —
    e.g. ``PipelineManagerAlreadyExistsError`` mapped to 409 — out of the error
    dashboards, while still covering the `INPUT`-domain 422 caller mistakes and
    the provider-429 passthrough without a second per-error-type registry.
    """
    return status >= 500


def _log_error_report(report: ErrorReport, *, request: Request, status: int | None = None) -> None:
    """Emit the structured error record for a handled `ErrorReport`.

    Disposition follows the final HTTP status (see ``_emit_at_error_level``):
    a 4xx is client-facing and logs at `warning` without a traceback (caller
    mistakes, the provider-429 passthrough, and API-level 4xx overrides like
    the 409 conflict), a 5xx logs at `error` with the traceback. The fields
    mirror the response so the two never drift.
    `user_id` rides every record when auth bound a caller — without it, the
    storage / pipeline-backend leg of a failure carries only `request_id` and
    `route`, and tying the failure to the caller requires correlating the
    request id across unrelated records (Phase 3 deleted the per-route
    `log.error(... user=...)` lines those failures used to emit).

    ``status`` defaults to ``report.http_status`` and exists so the caller can
    pass the post-override value (see ``_ERROR_TYPE_STATUS_OVERRIDES``) — the
    record then agrees with the HTTP status actually sent rather than the
    domain default.
    """
    effective_status = status if status is not None else report.http_status
    fields: dict[str, Any] = {
        "event": API_ERROR_EVENT,
        **_request_fields(request),
        "error_type": report.error_type,
        "error_category": report.error_category,
        "error_domain": report.error_domain,
        "retryable": report.retryable,
        "status": effective_status,
        "provider": report.provider,
        "model": report.model,
    }
    metadata = report.provider_metadata
    if metadata is not None:
        fields["provider_status_code"] = metadata.status_code
        fields["provider_request_id"] = metadata.request_id
    _emit_api_error(fields=fields, as_error=_emit_at_error_level(effective_status))


def _log_api_authored_error(*, document: dict[str, Any], status: int, request: Request) -> None:
    """Emit the structured error record for an API-authored error response.

    Shares the disposition rule and the common-key set of `_log_error_report`
    so every error response — a pipelex `ErrorReport` translated to RFC 7807
    *or* an API-authored 4xx/5xx raised by an `pipelex_api.errors` helper — produces
    one `event=api_error` record a downstream sink can filter uniformly on
    `event`, `request_id`, `route`, `error_type`, `error_domain`, `retryable`,
    and `status`. Without this, an API-owned 500 (a `raise_internal_server_error`
    site — `/version`'s missing-package case is the canonical example)
    would land with zero operator output, since `handle_api_error` only
    serializes the response.

    Where the two helpers differ — by design, matching what each side actually
    has to log:
    - API-authored docs add `detail`, always safe because
      `build_problem_document_from_api_error` does not apply strict-disclosure
      redaction (only `build_problem_document` does for pipelex domain errors).
      Carrying the message preserves the operator-facing cause in the record.
    - API-authored docs omit `error_category`, `provider`, `model`, and
      `provider_metadata.*` — those are inference-domain classifiers pipelex
      sets only on classifiable failures and the API never authors itself.

    A 4xx logs at `warning` without a traceback; a 5xx logs at `error` with
    the traceback — same status-keyed disposition rule `_log_error_report`
    uses (see ``_emit_at_error_level``), so a sink dedup'ing by level sees one
    shape.
    """
    fields: dict[str, Any] = {
        "event": API_ERROR_EVENT,
        **_request_fields(request),
        "error_type": document.get("error_type"),
        "error_domain": document.get("error_domain"),
        "retryable": document.get("retryable"),
        "status": status,
        "detail": document.get("detail"),
    }
    _emit_api_error(fields=fields, as_error=_emit_at_error_level(status))


def _json_safe_report(report: ErrorReport) -> ErrorReport:
    """Return a report whose floats Starlette's JSON encoder can render.

    `JSONResponse` encodes with `allow_nan=False`, so a non-finite
    `provider_metadata.retry_after_seconds` — a provider sending `Retry-After:
    inf` / `nan`, which pipelex's header parser passes through unchecked —
    would crash the whole response render, not just the `Retry-After` header.
    Null the unusable hint out; the rest of the report renders intact.
    """
    metadata = report.provider_metadata
    if metadata is None:
        return report
    seconds = metadata.retry_after_seconds
    if seconds is None or math.isfinite(seconds):
        return report
    safe_metadata = metadata.model_copy(update={"retry_after_seconds": None})
    return report.model_copy(update={"provider_metadata": safe_metadata})


_ERROR_TYPE_STATUS_OVERRIDES: dict[str, int] = {
    # Async execution disabled is a deliberate deployment configuration, not
    # an unexpected runtime fault. Mapping it to 501 Not Implemented (rather
    # than the CONFIG-domain default of 500) tells clients "this server does
    # not provide this functionality" without inviting retries.
    "AsyncExecutionNotEnabledError": 501,
    # A submission reusing a pipeline_run_id that is still registered (a
    # genuinely concurrent duplicate — completed/failed runs free their entry
    # on the way out) is a client-visible conflict, not a server fault.
    # Mapping it to 409 Conflict (rather than the no-domain default of 500)
    # tells clients "this id is currently in use": resubmit after the
    # in-flight run finishes, or pick a fresh id.
    "PipelineManagerAlreadyExistsError": 409,
    # The `method_ref` resolution failures (pipelex `MethodRefError` subclasses). The library
    # declares no `error_domain` on them, so without an override each would default to 500 —
    # wrong for what are overwhelmingly caller-fixable conditions. Each entry keeps the class
    # name as the distinct `error_type` the caller (or an agent) branches on:
    #   - A reference that does not match the `<address>[@<tag>]` grammar: the caller's own
    #     input, plainly fixable → 422.
    "MethodRefParseError": 422,
    #   - The repository could not be fetched (nonexistent repo, a `@tag` that is not a tag,
    #     network refusal). The dominant cause is a mistyped address or tag — caller-fixable —
    #     so 422; the message carries git's own explanation for the rarer upstream faults.
    "MethodFetchError": 422,
    #   - The repository was fetched but holds no package matching the address by manifest
    #     identity: the referenced resource does not exist → 404 (mirroring the hosted
    #     platform's unknown-`method_id` mapping); the message lists what the repo does contain.
    "MethodPackageNotFoundError": 404,
    #   - More than one package matches the address: the caller must disambiguate with the
    #     package's full address → 422.
    "MethodPackageAmbiguityError": 422,
    #   - The selected package exceeds the fetched-package ceilings: the referenced content
    #     cannot be processed under this deployment's bounds → 422 (not 413, which is about
    #     the request entity itself).
    "MethodPackageTooLargeError": 422,
    #   - The method's Python declares structure classes, whether it was sent as a bundle or
    #     fetched by `method_ref`: a policy refusal (hosted execution accepts MTHDS concepts and
    #     sandboxed PipeFuncs, not in-process Python) → 403, the same status as the bundle
    #     transport's custom-code gate.
    "MethodStructuresRefusedError": 403,
}


def _http_status_for(report: ErrorReport) -> int:
    """Return the HTTP status to use for this report.

    Defers to ``report.http_status`` for the standard mapping (provider-429
    passthrough + ``error_domain`` -> 4xx/5xx) and applies a per-error-type
    override last. Overrides live in ``_ERROR_TYPE_STATUS_OVERRIDES`` so the
    decisions are discoverable in one place — keep the dict small and each
    entry justified.
    """
    return _ERROR_TYPE_STATUS_OVERRIDES.get(report.error_type, report.http_status)


def _problem_response(report: ErrorReport, *, request: Request, disclosure_mode: DisclosureMode) -> JSONResponse:
    """Build the RFC 7807 `JSONResponse` for an `ErrorReport` and log the entry.

    Shared by the `PipelexError` handler and every orchestrator-mapper handler:
    both produce an `ErrorReport`, so both render and log it identically. The report is first
    made JSON-safe (see `_json_safe_report`); the status code then comes from
    `_http_status_for(report)` (the report's own mapping plus any API-layer
    override registered in ``_ERROR_TYPE_STATUS_OVERRIDES``), and the response
    body from the Phase 1 problem-document builder under the caller-supplied
    `disclosure_mode` (`register_exception_handlers` binds the app's effective
    mode into the handlers it registers).
    """
    report = _json_safe_report(report)
    request_id = request_id_of(request)
    status = _http_status_for(report)
    document = build_problem_document(
        report,
        instance=request.url.path,
        request_id=request_id,
        disclosure_mode=disclosure_mode,
    )
    # Keep the RFC 7807 ``status`` member aligned with the actual HTTP status
    # when an API-layer override has bumped it away from ``report.http_status``;
    # otherwise the two surfaces (header vs body) would silently disagree.
    document["status"] = status
    _log_error_report(report, request=request, status=status)
    return JSONResponse(
        status_code=status,
        content=document,
        media_type=PROBLEM_JSON_MEDIA_TYPE,
        headers=_retry_after_header(report),
    )


def problem_response_from_error_report(report: ErrorReport, *, request: Request) -> JSONResponse:
    """Render an `ErrorReport` value through the same RFC 7807 path as raised errors.

    Most `ErrorReport`s reach this module by raising a `PipelexError` or by an
    orchestrator transport mapper. `/validate` can also receive an `ErrorReport`
    as a registry-returned value; when that value is a backend/config/runtime
    fault rather than a validation verdict, it must still keep the same status,
    disclosure, logging, and retry headers as the global handler path.
    """
    disclosure_mode = getattr(request.app.state, "error_disclosure_mode", DisclosureMode.VERBOSE)
    return _problem_response(report, request=request, disclosure_mode=disclosure_mode)


async def handle_pipelex_error(request: Request, exc: Exception, *, disclosure_mode: DisclosureMode) -> Response:
    """Translate any pipelex `PipelexError` into an RFC 7807 problem response.

    The single place in the API that consumes a `PipelexError`'s `ErrorReport`.
    `to_error_report()` walks the `__cause__` chain, so a wrapper exception
    still surfaces the classification of the underlying failure. `exc` is typed
    `Exception` to match Starlette's handler contract; FastAPI only routes a
    `PipelexError` here, so the cast is sound. An orchestrator's workflow
    failure that is itself a `PipelexError` (e.g. the Temporal plugin's
    `WorkflowExecutionError`, which already carries a structured `ErrorReport`)
    resolves here via Starlette's MRO walk; only a *bare* orchestrator-SDK
    transport error (no `PipelexError` in its MRO) is routed to that plugin's
    own mapper-backed handler instead.
    """
    report = cast("PipelexError", exc).to_error_report()
    return _problem_response(report, request=request, disclosure_mode=disclosure_mode)


def _make_orchestrator_error_handler(mapper: HttpErrorMapperFn, *, disclosure_mode: DisclosureMode) -> "_ExceptionHandler":
    """Wrap one plugin-contributed error mapper into a FastAPI exception handler.

    The plugin owns the *classification* (it maps its bare transport/runtime
    exception — e.g. `temporalio.TemporalError` — to a structured `ErrorReport`);
    core owns the *transport* exception type (resolved lazily by the registrar);
    the API owns the *presentation* (the same RFC 7807 + `DisclosureMode`
    rendering every `ErrorReport` gets via `_problem_response`). This is what
    lets the base render an orchestrator's transport fault correctly while
    naming — and importing — no orchestrator SDK. `exc` is typed `Exception` to
    match Starlette's handler contract; FastAPI only routes the mapper's
    registered `exc_type` here.
    """

    async def _handler(request: Request, exc: Exception) -> Response:
        report = mapper(exc)
        return _problem_response(report, request=request, disclosure_mode=disclosure_mode)

    return _handler


async def handle_unexpected_error(request: Request, exc: Exception) -> Response:
    """Catch-all for any failure matched by no more-specific handler.

    Covers anything that is not an `ApiError`, a `RequestValidationError`, a
    `PipelexError`, or an orchestrator plugin's mapped transport exception — so on
    the orchestrator-agnostic base (which installs no mapper), an *unmapped* bare
    transport/runtime error collapses here to a 500.

    One of the two `except Exception`-equivalent sites the project sanctions —
    the outermost handler of an API. Disclosure follows the app's
    `disclosure_mode`, exactly like every other handler in this module: VERBOSE
    puts `Class: message` in `detail` so a caller can see what actually broke;
    STRICT keeps the fully sanitized body (no exception class, no `str(exc)`).
    A traceback reaches the client in neither mode — the class name and full
    traceback go to the operator log, correlated by request id.

    Honoring the mode here is what stops the catch-all from being a silent hole.
    An unclassified failure is *precisely* the one a caller cannot diagnose from
    a request id alone, and it is the only response in the API that used to
    contradict a deployment's explicit choice to disclose: a VERBOSE deployment
    got real messages for every classified error and a dead end for the one
    error nobody classified. STRICT still redacts, so a deployment that wants
    nothing leaked keeps that.

    The mode is read off `app.state` (like `problem_response_from_error_report`)
    rather than bound as a parameter, so registering this handler stays
    signature-free.

    This handler also covers a failure *inside* another handler (e.g. a corrupt
    `to_error_report()`): Starlette's `ServerErrorMiddleware` wraps the others,
    so such a failure still lands here rather than a bodyless default.
    """
    request_id = request_id_of(request)
    _emit_api_error(
        fields={
            "event": API_ERROR_EVENT,
            **_request_fields(request),
            "error_type": type(exc).__name__,
            "error_category": "unknown",
            "error_domain": ErrorDomain.RUNTIME,
            "status": 500,
        },
        as_error=True,
    )
    disclosure_mode = getattr(request.app.state, "error_disclosure_mode", DisclosureMode.VERBOSE)
    if disclosure_mode is DisclosureMode.STRICT:
        detail = "An unexpected error occurred. The request id is included for support."
    else:
        detail = f"{type(exc).__name__}: {exc}"
    # Route through the same builder every other API-authored 500 uses, so the
    # catch-all shape never drifts from `handle_api_error`'s output. The one
    # catch-all-specific addition is `error_category: "unknown"` — by definition
    # the failure was not classifiable, and the marker lets a downstream sink
    # tell a catch-all 500 apart from a classified `CONFIG`-domain one.
    document = build_problem_document_from_api_error(
        ErrorType.INTERNAL_SERVER_ERROR,
        detail,
        500,
        instance=request.url.path,
        request_id=request_id,
        error_domain=ErrorDomain.RUNTIME,
    )
    document["error_category"] = "unknown"
    return JSONResponse(status_code=500, content=document, media_type=PROBLEM_JSON_MEDIA_TYPE)


async def handle_api_error(request: Request, exc: Exception) -> Response:
    """Render an API-authored `ApiError` as an RFC 7807 problem response.

    `ApiError` is raised by the `raise_*` helpers in `pipelex_api.errors` for the API's
    own 4xx/5xx — request validation, auth, payload limits, misconfiguration.
    The helper builds the problem document at raise time, where it holds no
    `Request`, so this handler stamps the two request-scoped members (`instance`
    and `request_id`) onto a copy of it — the same two values, read from the same
    place, as the pipelex-error and request-validation paths use. It then
    serializes that document, re-attaches any `WWW-Authenticate` challenge header,
    and emits the structured `event=api_error` record so an API-owned 500 from any
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
    # Same `event=api_error` record as an explicit `raise_validation_error`,
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
    disclosure_mode: DisclosureMode = DisclosureMode.VERBOSE,
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

    `http_error_mappers` is the `{exc_type: to_error_report}` map an orchestrator
    plugin contributes through the plugin SPI (`PluginRegistrar.add_http_error_mapper`,
    read back via `get_http_error_mappers`). The caller resolves it at app
    construction — `pipelex_api.main` builds the registrar and passes it; the base resolves
    an empty map (it installs no orchestrator plugin), so no transport handler is
    registered and the only fallback for an unclassified failure stays the catch-all
    500. Each entry registers one handler that runs the mapper and renders the
    resulting `ErrorReport` through the shared RFC 7807 + disclosure path — so core
    and the API name no orchestrator SDK. Keeping the parameter explicit (rather than
    calling `build_registrar` in here) preserves this module's import-side-effect-free
    contract: tests register handlers on a throwaway app without a booted Pipelex, and
    a test contributes a synthetic mapper to prove the seam without installing a plugin.

    `disclosure_mode` is captured by the handlers that render a pipelex `ErrorReport`
    (`handle_pipelex_error` and every mapper handler) via the closures below —
    production passes the startup-resolved value (`pipelex_api.main.ERROR_DISCLOSURE_MODE`);
    tests pass whatever the test needs and the default (`VERBOSE`) covers the common
    case. The other handlers don't render an `ErrorReport`, so they register
    directly — `handle_unexpected_error` still honors the mode, reading it back off
    `app.state` (set below) rather than through a closure.
    """
    app.state.error_disclosure_mode = disclosure_mode

    async def _pipelex_error(request: Request, exc: Exception) -> Response:
        return await handle_pipelex_error(request, exc, disclosure_mode=disclosure_mode)

    app.add_exception_handler(ApiError, handle_api_error)
    app.add_exception_handler(RequestValidationError, handle_request_validation_error)
    app.add_exception_handler(ClientDisconnect, handle_client_disconnect)
    app.add_exception_handler(PipelexError, _pipelex_error)
    for exc_type, mapper in (http_error_mappers or {}).items():
        app.add_exception_handler(exc_type, _make_orchestrator_error_handler(mapper, disclosure_mode=disclosure_mode))
    app.add_exception_handler(Exception, handle_unexpected_error)
