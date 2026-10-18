"""Global FastAPI exception handlers that translate any failure into RFC 9457.

The single place the API renders a failure into an HTTP response. Every
handler produces the same `application/problem+json` shape, a problem document
with a registry code: every `PipelexError` becomes its problem document
(`PipelexError.to_problem`), the runner's own refusals included, which it raises
as the classes of `pipelex_api.exceptions`; a FastAPI `RequestValidationError`
from automatic request validation becomes `request.invalid`, one item per
refused field; a route nobody serves is `request.not_found`, a method a route
does not accept `request.method_not_allowed`, and any other refusal the
framework raises while reading a request `request.malformed`; a client gone
mid-upload is `request.malformed` too; each orchestrator plugin's
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

import traceback
from collections.abc import Awaitable, Callable
from enum import StrEnum, unique
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, cast

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from mthds.protocol.problem.registry import CoreCode, ProblemDomain
from pipelex import log
from pipelex.base_exceptions import ErrorDomain, PipelexError, iter_traceback_chain
from pipelex.cogt.exceptions import find_inference_error_category_in_chain
from pipelex.errors.problem import PipelexProblem, ProblemDiagnostics, ProblemView
from pipelex.errors.security_event import emit_security_event
from pipelex.pipe_run.located_failure import make_unexpected_failure
from pipelex.plugins.registrar import HttpErrorMapperFn
from pipelex.system.telemetry.otel_constants import OTelLogAttr
from pipelex.tools.log.error_fields import ERROR_TYPE_FIELD
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import ClientDisconnect
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from pipelex_api.exceptions import RunnerAuthError, RunnerRequestError
from pipelex_api.middleware import request_id_of
from pipelex_api.problem_document import problem_json_response, problem_status
from pipelex_api.problem_view import problem_view_of
from pipelex_api.request_refusals import callback_url_refusal_in, refused_request_error

if TYPE_CHECKING:
    from pipelex_api.security import RequestUser

# A Starlette/FastAPI async exception handler: `(request, exc) -> response`.
_ExceptionHandler = Callable[[Request, Exception], Awaitable[Response]]

# The classes of the exceptions a failure's chain holds, by name, outermost first: what each one was raised from or
# while handling, as a traceback would print them, without their text.
ERROR_CHAIN_FIELD = "error.chain"

# Where the deepest exception of the chain was raised, as `file:line in function` from the outermost frame inward,
# without the source lines or any exception's text. Written on a 5xx alone, the failure an operator debugs.
ERROR_FRAMES_FIELD = "error.frames"

# The prefix of the fields carrying the problem's operator-only parameters, one field per parameter, such as
# `error.params.component`. The registry marks a parameter operator-only when it names the runtime's own configuration
# or one of its components, never a caller's content, so the record carries them whatever view the response took.
ERROR_PARAMS_FIELD_PREFIX = "error.params."


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


def _run_extras_of(request: Request) -> dict[str, str] | None:
    """Return the labels the request's body named, its `analytics_groups`, when they were bound on the request.

    The opaque labels a host attaches to a request, which the hosted plane fills with the organization. They ride
    the security event a refusal answered here logs, so a refusal before any run exists still names whose
    request it was. Bound as soon as a JSON body is parsed (`pipelex_api.run_extras_binding`); `None` for a request
    with no JSON body, or a body naming no labels or labels that did not validate.
    """
    return getattr(request.state, "run_extras", None)


def _request_fields(request: Request) -> dict[str, Any]:
    """Return the request-scoped attributes every error record carries.

    Single source of truth for the `url.path` / `user.id` / `pipe_code` /
    `pipeline_run_id` set, which every record `_log_problem` emits carries. The
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


@unique
class RecordLevel(StrEnum):
    """The level of the record an error response writes, which decides whether it reaches the error-rate alerts.

    `ERROR` for a failure whoever runs the server must look at, with the frames its deepest exception was raised through;
    `WARNING` for a failure the caller caused or can avoid, without frames; `DEBUG` for a request no route serves, which
    scanners send by the thousand and which nobody has anything to do about.
    """

    DEBUG = "debug"
    WARNING = "warning"
    ERROR = "error"

    @property
    def writes_frames(self) -> bool:
        """Whether the record names where the deepest exception of the chain was raised, which only an operator's fault needs."""
        match self:
            case RecordLevel.ERROR:
                return True
            case RecordLevel.WARNING | RecordLevel.DEBUG:
                return False


def _emit_api_error(*, fields: dict[str, Any], level: RecordLevel) -> None:
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
    absent rather than carried as a null. `level` is the record's (`RecordLevel`). No record
    carries the exception itself, whose traceback would print the text of every
    exception of its chain, and a foreign exception's text, a pydantic
    `ValidationError`'s or a method function's, can quote a run's inputs or a
    model's answer: the record names the chain's classes and where the deepest
    was raised instead (`_chain_fields`), with the problem's operator-only
    parameters, which name the runtime's own configuration or component, such as
    the `component` of a `runtime.misconfigured`. The capped message rides the
    operator view's diagnostics alone, which only a request the operator
    authenticated reads in its response.
    """
    attributes = {key: value for key, value in fields.items() if value is not None}
    match level:
        case RecordLevel.ERROR:
            log.error("A request ended in an error response", fields=attributes)
        case RecordLevel.WARNING:
            log.warning("A request ended in an error response", fields=attributes)
        case RecordLevel.DEBUG:
            log.debug("A request ended in an error response", fields=attributes)


def _chain_fields(error: BaseException, *, with_frames: bool) -> dict[str, Any]:
    """The record fields naming a failure's exceptions by class, and with `with_frames` where the deepest was raised.

    Never an exception's text: the classes and the frames are this server's code, while a message can be anyone's data.
    """
    chain = list(iter_traceback_chain(error))
    fields: dict[str, Any] = {ERROR_CHAIN_FIELD: [type(link).__name__ for link in chain]}
    if with_frames:
        deepest = chain[-1]
        frames = traceback.StackSummary.extract(traceback.walk_tb(deepest.__traceback__), lookup_lines=False)
        fields[ERROR_FRAMES_FIELD] = [f"{frame.filename}:{frame.lineno} in {frame.name}" for frame in frames]
    return fields


def _operator_param_fields(*, diagnostics: ProblemDiagnostics | None) -> dict[str, Any]:
    """The record fields carrying a problem's operator-only parameters, one per parameter, under `error.params.`.

    The operator view keeps them in its diagnostics, which a caller's response leaves out, so the record is where the
    operator reads them whatever view the response took: the `component` of a `runtime.misconfigured`, the `dependency`
    of a `runtime.unavailable`, the setting or the file of a `pipelex.config.*`. The registry declares a parameter
    operator-only when it names the runtime's own configuration or one of its components, never a caller's content, so
    no run data reaches the record through them.
    """
    if diagnostics is None or not diagnostics.params:
        return {}
    return {f"{ERROR_PARAMS_FIELD_PREFIX}{name}": value for name, value in diagnostics.params.items()}


def record_level_of(*, status: int, domain: ProblemDomain) -> RecordLevel:
    """The level of an error response's record, from its status and from who must act on it, its code's domain.

    A 4xx is the caller's to act on, a mistake or a benign conflict such as ``pipelex.run.already_exists`` answered with
    409, so it logs at `warning`. A 5xx logs at `error` only when the server has something to fix:

    - a `501` states that this deployment does not offer what the request asks for, custom code without a sandbox,
      `/v1/start` on a blocking-only orchestrator, a model it serves no backend for. The operator decides whether to
      offer it, but nothing is broken, and the caller meets the refusal each time it asks again, so it logs at `warning`,
      or any caller could fill the error-rate alerts by repeating it;
    - any other 5xx logs at `warning` when its domain is the caller's (`input`, `method`, `account`), a refusal the
      caller can avoid, such as a webhook receiver of its own that refused a delivery, and at `error` when it is the
      runtime's or the operator's.
    """
    if status < 500 or status == HTTPStatus.NOT_IMPLEMENTED:
        return RecordLevel.WARNING
    match domain:
        case ProblemDomain.INPUT | ProblemDomain.METHOD | ProblemDomain.ACCOUNT:
            return RecordLevel.WARNING
        case ProblemDomain.OPERATOR | ProblemDomain.RUNTIME:
            return RecordLevel.ERROR


def _log_problem(problem: PipelexProblem, *, error: BaseException | None, request: Request, status: int, level: RecordLevel | None) -> None:
    """Emit the structured error record for a failure answered with a problem, from the operator view.

    Its level is `level` when the caller names one, else follows the HTTP status and the code's domain
    (``record_level_of``): a 4xx is client-facing and logs at `warning` (caller mistakes, a provider's 429 passed through,
    and the 409 conflict), a 5xx the server has to fix logs at `error` with the frames its deepest exception was raised
    through. No record carries an
    exception's text or its traceback (``_emit_api_error``). `error.code` is the
    problem's code, `error.type` the class of the exception that escaped, else
    the class the operator view names, and `error.chain` the classes of the
    exceptions it was raised from, and each operator-only parameter of the problem
    rides `error.params.<name>`. `user.id` rides every record when auth bound a caller —
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
    # The class that escaped, which for an exception that is not a PipelexError is not the stand-in the problem was
    # built from; a failure received as a value has its problem's class alone.
    error_class: str | None = None
    if error is not None:
        error_class = type(error).__name__
    elif diagnostics is not None:
        error_class = diagnostics.error_class
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
    fields.update(_operator_param_fields(diagnostics=diagnostics))
    record_level = level or record_level_of(status=status, domain=problem.effective_domain)
    if error is not None:
        fields.update(_chain_fields(error, with_frames=record_level.writes_frames))
    _emit_api_error(fields=fields, level=record_level)


def problem_response(
    problem: PipelexProblem,
    *,
    error: BaseException | None,
    request: Request,
    headers: dict[str, str] | None = None,
    status: int | None = None,
    record_level: RecordLevel | None = None,
) -> JSONResponse:
    """Render a problem built in the operator's view as the response to `request`, and log the failure.

    The single rendering of every failure a problem describes: a raised `PipelexError`, the runner's own refusals
    included, an orchestrator plugin's mapped transport fault, an unexpected exception, and a fault the `/validate` route
    receives as a value rather than a raise, for which `error` is `None`. The status is the code's, unless `status` names
    the one a framework refusal keeps; the record is logged from the operator view, at `record_level` when the caller
    names one, else at the level its status and its code's domain give it (`record_level_of`), and the body is the view
    of the request's reader (`pipelex_api.problem_view`), rendered by `pipelex_api.problem_document.problem_json_response`,
    which adds `headers` to the ones its status calls for.
    """
    answered_status = status or problem_status(problem)
    _log_problem(problem, error=error, request=request, status=answered_status, level=record_level)
    return problem_json_response(problem, view=problem_view_of(request), headers=headers, status=answered_status)


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
    # A security refusal logs its security event, once: a run's boundary already reported a refusal it saw, and
    # one refused before any run exists, or by a route around the runner, is reported here. The request id is
    # the log context's, which `RequestIdMiddleware` binds for the whole request. No run id: the one a body names
    # is the caller's claim, and no run the runtime assigned one to exists yet.
    emit_security_event(error=error, extras=_run_extras_of(request))
    return problem_response(operator_problem_of(error, request=request), error=error, request=request, headers=_challenge_headers(error))


def _challenge_headers(error: PipelexError) -> dict[str, str] | None:
    """The `WWW-Authenticate` challenge of an authentication refusal that names one, the scheme the deployment reads.

    A refusal behind a trusted proxy names none: that deployment reads no credential of the request, so a challenge
    would ask for one it never reads.
    """
    if isinstance(error, RunnerAuthError) and error.challenge is not None:
        return {"WWW-Authenticate": error.challenge}
    return None


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

    Covers anything that is not a `RequestValidationError`, a `ClientDisconnect`, a
    Starlette `HTTPException`, a `PipelexError`, or an orchestrator plugin's mapped
    transport exception — so on
    the orchestrator-agnostic base (which installs no mapper), an *unmapped* bare
    transport/runtime error collapses here to a 500.

    One of the two `except Exception`-equivalent sites the project sanctions —
    the outermost handler of an API. The exception is stood in for by a
    `PipelexUnexpectedError` (`make_unexpected_failure`) and answered as its
    problem, `runtime.unexpected`, through the same rendering as every other
    failure: the caller reads the code's own sentences and never the exception's
    text, and a request the operator authenticated reads its class and message in
    `diagnostics`. Neither a traceback nor the exception's text reaches the
    response or the log: the operator's record names the chain's classes and the
    frames it was raised through, correlated by request id.

    This handler also covers a failure *inside* another handler: Starlette's
    `ServerErrorMiddleware` wraps the others, so such a failure still lands here
    rather than a bodyless default. That middleware raises the exception again
    once this handler answered it, for the server to log with its traceback;
    `AnsweredErrorBarrier` stops it there, so its text reaches no log either.
    """
    unexpected_failure = make_unexpected_failure(error=exc)
    response = problem_response(operator_problem_of(unexpected_failure, request=request), error=exc, request=request)
    # Marked once its record is written, so `AnsweredErrorBarrier` tells the exception Starlette raises again after this
    # answer from one nothing recorded.
    request.state.answered_error = exc
    return response


async def handle_request_validation_error(request: Request, exc: Exception) -> Response:
    """Answer FastAPI's automatic request validation failure as `request.invalid`, one item per refused field.

    FastAPI raises `RequestValidationError` when a request body, query, or path parameter fails the endpoint's declared
    model: an extra field under `extra="forbid"`, a length breach, a missing or mistyped field, a `field_validator`
    raising `ValueError`. Its built-in handler would answer a bare `{"detail": [...]}` in `application/json`; this
    handler answers the runner's own refusal instead (`pipelex_api.request_refusals`), `request.invalid` with one item
    per refused field, or `request.malformed` for a body that is not JSON, through the same rendering every pipelex error
    takes. A callback URL the SSRF rules refuse is found among the faults and answered as its own security refusal,
    whichever route's model ran the check. `exc` is typed `Exception` to match Starlette's handler contract; FastAPI only
    routes a `RequestValidationError` here, so the cast is sound.
    """
    validation_error = cast("RequestValidationError", exc)
    faults = validation_error.errors()
    # A callback URL refusal is the error the model's validator raised, answered as itself; any other fault is answered by
    # a refusal standing in for FastAPI's exception, chained from it so the record's `error.chain` still names it.
    refusal = callback_url_refusal_in(faults=faults) or _standing_in_for(
        refused_request_error(faults=faults, located_by_request_part=True), original=validation_error
    )
    return await handle_pipelex_error(request, refusal)


def _standing_in_for(refusal: PipelexError, *, original: Exception) -> PipelexError:
    """`refusal`, chained from the framework exception it answers in its place, as `raise refusal from original` would chain it.

    A handler answering a framework exception through one of the runner's refusals builds that refusal itself, so nothing
    raises it from the exception it stands in for. Chained, the record's `error.chain` names the framework exception
    after the refusal, and the operator view's `diagnostics.causes` name its class, never its text.
    """
    refusal.__cause__ = original
    refusal.__suppress_context__ = True
    return refusal


# The reason a body the client stopped sending is malformed, which none of the reasons `request.malformed` lists names.
_BODY_INCOMPLETE_REASON = "body_incomplete"


async def handle_client_disconnect(request: Request, exc: Exception) -> Response:
    """Answer a client that left before its request body arrived in full as `request.malformed`, logged as a caller's failure.

    Starlette raises `ClientDisconnect` from a body read when the client goes away mid-upload: from the nesting check of a
    `JsonBodyRoute`, and from the run routes, which read their raw body themselves. Nobody is left to read the answer, so
    what matters is the record it leaves: a 422 at `warning`, a caller's failure, never a 500 server fault logged with a
    traceback. The body that arrived is cut short, so it is malformed; no reason the code lists fits a truncated body,
    and its reason takes any string beside them, so the runner names this one itself.
    """
    message = "The client disconnected before the request body was received in full"
    refusal = RunnerRequestError(message).with_error_code(CoreCode.REQUEST_MALFORMED).with_params(reason=_BODY_INCOMPLETE_REASON)
    return await handle_pipelex_error(request, _standing_in_for(refusal, original=exc))


# The reason a body the framework refused to read is malformed, for a refusal no check of the runner's own made first.
_BODY_UNREADABLE_REASON = "unreadable"

# The reason a body the framework refused as too large is malformed: the framework names no limit and no size, which the
# runner's `request.too_large` must state, so the refusal is the reading's, and keeps its 413.
_BODY_TOO_LARGE_REASON = "too_large"

# The component a rate limit in front of a route is, which the operator reads on the record of the 429 it answered.
_RATE_LIMITER_DEPENDENCY = "rate_limiter"

# The one header a framework refusal of each status keeps, the one its answer needs: the methods a route accepts on a
# 405, the challenge a credential refusal names on a 401, and the delay a rate limit asks for on a 429. Any other header
# it was raised with is dropped. Compared in lower case, as HTTP header names are.
_KEPT_FRAMEWORK_HEADER_BY_STATUS: dict[int, str] = {401: "www-authenticate", 405: "allow", 429: "retry-after"}


def framework_refusal(*, status: int, challenge: str | None) -> tuple[PipelexError, int | None]:
    """The runner's refusal answering a 4xx the framework raised, and the status it keeps when its code declares another.

    Each refusal carries a code whose required parameters it can fill: the framework says nothing about a refusal but its
    status and a header, so a code whose parameters it cannot know gives way to one whose parameters it can.

    - a 400, or a 422 raised as an `HTTPException`, is a request the framework could not read, `request.malformed`;
    - a 401 is `auth.missing_credential`, with the challenge the raise named;
    - a 403 is `auth.invalid_credential`, keeping its 403: `auth.forbidden` would need the `requirement` the identity
      lacks, which the framework does not say;
    - a 404 and a 405 are a request no route serves, `request.not_found` and `request.method_not_allowed`;
    - a 413 is `request.malformed` with the reason `too_large`, keeping its 413: `request.too_large` states a limit and a
      size, which the framework does not say;
    - a 429 is `runtime.unavailable`, whose verdict invites a retry after the `Retry-After` the raise named, keeping its
      429, with the rate limiter as the dependency the operator reads: `account.rate_limited` would need the limit and
      the window, which the framework does not say;
    - any other 4xx, a 415 among them, is `request.malformed` with the reason `unreadable`, keeping its status: a form
      of request the framework would not read.
    """
    refusal: PipelexError
    kept_status: int | None = None
    match status:
        case 400 | 422:
            message = f"The framework refused to read the request with HTTP {status}"
            refusal = RunnerRequestError(message).with_error_code(CoreCode.REQUEST_MALFORMED).with_params(reason=_BODY_UNREADABLE_REASON)
        case 401:
            message = "The framework refused the request for want of a credential"
            refusal = RunnerAuthError(message, challenge=challenge).with_error_code(CoreCode.AUTH_MISSING_CREDENTIAL)
        case 403:
            message = "The framework refused the request: its credential does not permit this operation"
            refusal = RunnerAuthError(message).with_error_code(CoreCode.AUTH_INVALID_CREDENTIAL)
            kept_status = status
        case 404:
            refusal = RunnerRequestError("No route serves this path").with_error_code(CoreCode.REQUEST_NOT_FOUND)
        case 405:
            refusal = RunnerRequestError("This route does not accept the request's method").with_error_code(CoreCode.REQUEST_METHOD_NOT_ALLOWED)
        case 413:
            message = "The framework refused the request as too large"
            refusal = RunnerRequestError(message).with_error_code(CoreCode.REQUEST_MALFORMED).with_params(reason=_BODY_TOO_LARGE_REASON)
            kept_status = status
        case 429:
            message = "A rate limit refused the request"
            refusal = RunnerRequestError(message).with_error_code(CoreCode.RUNTIME_UNAVAILABLE).with_params(dependency=_RATE_LIMITER_DEPENDENCY)
            kept_status = status
        case _:
            message = f"The framework refused the request with HTTP {status}, a status no registry code declares"
            refusal = RunnerRequestError(message).with_error_code(CoreCode.REQUEST_MALFORMED).with_params(reason=_BODY_UNREADABLE_REASON)
            kept_status = status
    return refusal, kept_status


# The statuses of the refusals Starlette's routing raises before any route runs, for a path nobody serves or a method its
# route does not accept, which scanners probing for `/wp-admin` or `/.env` send by the thousand.
_ROUTING_STATUSES = frozenset({HTTPStatus.NOT_FOUND, HTTPStatus.METHOD_NOT_ALLOWED})


async def handle_http_exception(request: Request, exc: Exception) -> Response:
    """Answer the refusals Starlette and FastAPI raise as `HTTPException`s as problems, never a client's 4xx as a 500.

    Starlette raises an `HTTPException` when routing fails before any route runs: a 404 for a path nobody serves, and a
    405 for a method the path's route does not accept, with the `Allow` header listing the methods it does. The framework
    raises one while it reads a request, too: FastAPI's 400 for a typed body its parse fails on with anything but a
    `JSONDecodeError`, and Starlette's 400 for a form it cannot parse, which `JsonBodyRoute` mostly answers first
    (`pipelex_api.json_body`). And a dependency the framework runs may raise one: FastAPI's security classes answer a
    missing credential with a 401 or a 403, a rate limiter with a 429. No route of the runner raises one itself (its
    refusals are the classes of `pipelex_api.exceptions`).

    Each 4xx keeps its meaning (`framework_refusal`): it is answered under a code whose meaning matches its own and whose
    parameters the runner can fill, keeping its status where that code declares another, and the one header it was
    raised with that its answer needs rides along, the `Allow` of a 405, the `WWW-Authenticate` challenge of a 401 or the
    `Retry-After` of a 429. A routing 404 or 405 writes its record at `DEBUG`, as Starlette's own answer wrote none: no one
    has anything to do about a path nobody serves, and a scanner probing for them would otherwise fill the warnings. A 5xx
    is the framework's own failure, `runtime.unexpected`. The refusal is chained from the `HTTPException`, so the record's
    `error.chain` names it. `exc` is typed `Exception` to match Starlette's handler contract; Starlette only routes an
    `HTTPException` here, so the cast is sound.
    """
    http_exception = cast("StarletteHTTPException", exc)
    status = http_exception.status_code
    if not 400 <= status < 500:
        return await handle_unexpected_error(request, http_exception)
    kept_header = _KEPT_FRAMEWORK_HEADER_BY_STATUS.get(status)
    kept_headers = {key: value for key, value in (http_exception.headers or {}).items() if key.lower() == kept_header}
    challenge = next(iter(kept_headers.values()), None) if kept_header == "www-authenticate" else None
    refusal, kept_status = framework_refusal(status=status, challenge=challenge)
    refusal = _standing_in_for(refusal, original=http_exception)
    record_level = RecordLevel.DEBUG if status in _ROUTING_STATUSES else None
    return problem_response(
        operator_problem_of(refusal, request=request),
        error=refusal,
        request=request,
        headers=kept_headers,
        status=kept_status,
        record_level=record_level,
    )


# The message of the record `AnsweredErrorBarrier` writes for a failure no handler recorded, once a response had started.
UNRECORDED_FAILURE_MESSAGE = "A request failed after its response had started"


class AnsweredErrorBarrier:
    """Pure-ASGI layer around the app that keeps an exception it answered from reaching the server that runs it.

    Starlette's `ServerErrorMiddleware` runs the catch-all handler (`handle_unexpected_error`) and then raises the
    exception again, so that the server can log it: uvicorn writes it with its traceback through its own logger,
    outside the runner's records, and a traceback prints the text of every exception of its chain, which a foreign
    exception can fill with a run's inputs or a model's answer. This layer sits outside that middleware and stops the
    exception there. When no response has started, which only a failure of the handler itself leaves, the failure is
    answered and logged here as the handler would have. Once one has, nothing can be answered any more: the exception
    the handler answered, which it marks once its record is written, is dropped, and any other, the handler's own
    failure while a response was streaming or sending, is dropped after a record of its own,
    `UNRECORDED_FAILURE_MESSAGE`, which names the request's path, the status already sent and the chain by class, never
    an exception's text. A failure of the barrier's own answer, the catch-all building it or the server sending it, such
    as to a client already gone, is recorded and dropped the same way. So no exception, and no text of one, leaves the
    app, and none leaves it unrecorded.

    `pipelex_api.main` puts it directly around the FastAPI app, inside `RequestIdMiddleware`, so the request's log
    context is still bound while it answers.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        sent_status: int | None = None

        async def tracking_send(message: Message) -> None:
            nonlocal sent_status
            if message["type"] == "http.response.start":
                sent_status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:  # ruff: ignore[BLE001]
            # The absolute root of an API endpoint handler, outside Starlette's own catch-all, which raises whatever
            # reached it again.
            request = Request(scope)
            if sent_status is not None:
                if getattr(request.state, "answered_error", None) is not exc:
                    _log_unrecorded_failure(exc, request=request, sent_status=sent_status)
                return
            try:
                response = await handle_unexpected_error(request, exc)
                await response(scope, receive, tracking_send)
            except Exception as answer_failure:  # ruff: ignore[BLE001]
                # The absolute root still: the barrier's own answer failed, the catch-all building it or the server
                # sending it, such as to a client already gone, and nothing is left to answer it.
                _log_unrecorded_failure(answer_failure, request=request, sent_status=sent_status)


def _log_unrecorded_failure(error: BaseException, *, request: Request, sent_status: int | None) -> None:
    """Record a failure no handler recorded, which ended a request after its response had started.

    The response's status and part of it are already sent, so the failure is answered by no problem: the record names the
    request's path, the status sent, the class that escaped and the classes of its chain, and never an exception's text.
    `sent_status` is `None` only when the barrier's own answer failed before its status was sent, which leaves the
    server to answer for it, and the record then names no status.
    """
    fields: dict[str, Any] = {
        "url.path": request.url.path,
        ERROR_TYPE_FIELD: type(error).__name__,
        **_chain_fields(error, with_frames=False),
    }
    if sent_status is not None:
        fields[OTelLogAttr.HTTP_RESPONSE_STATUS_CODE] = sent_status
    log.error(UNRECORDED_FAILURE_MESSAGE, fields=fields)


def register_exception_handlers(
    app: FastAPI,
    *,
    http_error_mappers: dict[type[Exception], HttpErrorMapperFn] | None = None,
) -> None:
    """Register the app-level exception handlers on `app`.

    Resolution is most-specific-first: a FastAPI `RequestValidationError` (automatic
    request-body / parameter validation) → `handle_request_validation_error`; a
    Starlette `ClientDisconnect` (the client left mid-upload) →
    `handle_client_disconnect`; a Starlette `HTTPException` (a path no route
    serves, a method a route does not accept) → `handle_http_exception`; a
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
    app.add_exception_handler(RequestValidationError, handle_request_validation_error)
    app.add_exception_handler(ClientDisconnect, handle_client_disconnect)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(PipelexError, handle_pipelex_error)
    for exc_type, mapper in (http_error_mappers or {}).items():
        app.add_exception_handler(exc_type, _make_orchestrator_error_handler(mapper))
    app.add_exception_handler(Exception, handle_unexpected_error)
