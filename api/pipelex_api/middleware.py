"""ASGI middleware shared across the FastAPI app."""

import secrets
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from mthds.protocol.problem.registry import CoreCode
from pipelex import log
from pipelex.errors.problem import ProblemView
from pipelex.system.job_metadata import is_valid_request_id
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from pipelex_api.exceptions import RunnerRequestError
from pipelex_api.limits import MAX_REQUEST_BODY_BYTES, MAX_REQUEST_BODY_MIB
from pipelex_api.problem_document import problem_json_response


def request_id_of(request: Request) -> str | None:
    """Return the correlation id `RequestIdMiddleware` stored on this request, or `None` when it did not run.

    `getattr` rather than attribute access: a request that never went through the middleware — a unit
    test issuing a bare ASGI call, a non-HTTP scope — simply has no id, and a reader of the id is not
    the place to discover that. This is the one way the API reads the id back; the runtime's bound log
    context carries the same value onto every record but is not a lookup table for anyone else.
    """
    return getattr(request.state, "request_id", None)


def _too_large_response(*, request: Request, size: int) -> JSONResponse:
    """Build the 413 `request.too_large` problem response for an over-limit request body.

    The body-size check runs in middleware, before routing, so no exception handler answers it: a middleware must
    `return` a response, not raise. It renders the same problem a `RunnerRequestError` carrying `request.too_large` would,
    in the caller's view, since no authentication has run yet to mark the request as the operator's.
    `RequestIdMiddleware` runs outermost, so the id is already on `request.state` by the time this is reached; that
    middleware's `send` wrapper also stamps the `X-Request-ID` header onto this response.

    Args:
        request: The refused request.
        size: The bytes the request reached: the length it declared, or the bytes read before the read was cut.
    """
    message = f"Request body exceeds the {MAX_REQUEST_BODY_MIB} MiB limit"
    refusal = RunnerRequestError(message).with_error_code(CoreCode.REQUEST_TOO_LARGE).with_params(limit=MAX_REQUEST_BODY_BYTES, size=size)
    problem = refusal.to_problem(view=ProblemView.OPERATOR, request_id=request_id_of(request))
    return problem_json_response(problem, view=ProblemView.CALLER)


async def request_body_size_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Reject requests whose body exceeds MAX_REQUEST_BODY_BYTES.

    Two layers of defense:
      1. Trust `Content-Length` header when present — fast reject before any body is read.
      2. For chunked / missing-header requests, wrap `receive` so we count bytes as
         they arrive. When the cumulative count crosses the cap, the over-limit
         chunk is NOT forwarded: it is replaced with an end-of-stream marker so
         `await request.body()` returns a bounded (often empty) body rather than
         the full oversized payload, and any further read keeps returning the
         same terminator (NOT `http.disconnect`, which would raise
         `ClientDisconnect` and escape past the 413 override). The 413 response
         then overrides whatever the route returned on its truncated input.
    """
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            declared = -1
        if declared > MAX_REQUEST_BODY_BYTES:
            return _too_large_response(request=request, size=declared)

    original_receive = request.receive
    bytes_seen = 0
    too_large = False

    async def counting_receive() -> Message:
        nonlocal bytes_seen, too_large
        if too_large:
            # Idempotent end-of-stream on every subsequent read. Returning
            # `http.disconnect` instead would raise `ClientDisconnect` in
            # Starlette's body reader, which would escape `call_next` as an
            # exception and bypass the 413 override below — the request would
            # land as a sanitized 500 instead of 413.
            return {"type": "http.request", "body": b"", "more_body": False}
        message = await original_receive()
        if message.get("type") == "http.request":
            body = message.get("body", b"")
            if isinstance(body, (bytes, bytearray)):
                bytes_seen += len(body)
                if bytes_seen > MAX_REQUEST_BODY_BYTES:
                    too_large = True
                    return {"type": "http.request", "body": b"", "more_body": False}
        return message

    request._receive = counting_receive  # type: ignore[assignment]  # noqa: SLF001

    response = await call_next(request)
    if too_large:
        return _too_large_response(request=request, size=bytes_seen)
    return response


# --- Request correlation -----------------------------------------------------

REQUEST_ID_HEADER = "X-Request-ID"

# Crockford's Base32 alphabet — the ULID encoding. Excludes I, L, O, U so a
# request id stays unambiguous if a human transcribes it out of a log.
_CROCKFORD_BASE32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ULID_LENGTH = 26
_ULID_RANDOM_BITS = 80
_ULID_TIMESTAMP_MASK = (1 << 48) - 1


def generate_request_id() -> str:
    """Generate a fresh ULID: a 26-char, time-sortable, URL-safe identifier.

    The high 48 bits encode a millisecond Unix timestamp, so ids sort by
    creation time; the low 80 bits are cryptographically random. The 128-bit
    value is rendered in Crockford Base32.
    """
    timestamp_ms = (time.time_ns() // 1_000_000) & _ULID_TIMESTAMP_MASK
    value = (timestamp_ms << _ULID_RANDOM_BITS) | secrets.randbits(_ULID_RANDOM_BITS)
    digits = [""] * _ULID_LENGTH
    for index in range(_ULID_LENGTH - 1, -1, -1):
        value, remainder = divmod(value, 32)
        digits[index] = _CROCKFORD_BASE32[remainder]
    return "".join(digits)


def _resolve_request_id(scope: Scope) -> str:
    """Return the request id for this request.

    Reuses a valid inbound `X-Request-ID` header; otherwise — absent,
    malformed, or over-long — mints a fresh ULID. An inbound id is reflected
    into response headers, logs and error bodies, so it is never trusted
    verbatim: it must pass the runtime's one request id rule
    (`pipelex.system.job_metadata.is_valid_request_id`), the one a run applies
    to the id it is handed, or it is discarded. ULIDs and UUIDs both pass.
    """
    for name, value in scope.get("headers", []):
        if name == b"x-request-id":
            candidate: str = value.decode("latin-1").strip()
            if is_valid_request_id(value=candidate):
                return candidate
            break
    return generate_request_id()


class RequestIdMiddleware:
    """Pure-ASGI middleware that assigns a correlation id to every HTTP request.

    For each request it reuses a valid inbound `X-Request-ID` or mints a fresh
    ULID, stores it on `request.state.request_id`, binds the runtime's log
    context to that id for the duration of the request, and echoes
    `X-Request-ID` on the response (success and error alike).

    Binding the runtime's context rather than an API-owned contextvar is what
    puts `request_id` on *every* record emitted underneath — the API's own
    error lines, and equally the ones pipelex emits from inside a run — as an
    attribute a structured sink indexes, with no call site having to pass it
    and no message having to interpolate it. The binding is in-process only: a
    run dispatched to a worker gets the id from its `RunMetadata`, where the
    run routes put it by passing `request_id_of(request)` to the runner.

    Applied in `pipelex_api.main` by wrapping the whole FastAPI app
    (`app = RequestIdMiddleware(app)`), NOT via `app.add_middleware()`.
    `add_middleware` always nests a middleware *inside* Starlette's
    `ServerErrorMiddleware`, which would leave it unable to bind the context
    for — or set a header on — the catch-all 500 that `ServerErrorMiddleware`
    emits. Wrapping the app puts this middleware genuinely outermost, outside
    `ServerErrorMiddleware`, so the context is bound and `X-Request-ID` is
    echoed on every response, the catch-all 500 included. Raw ASGI (rather than
    `BaseHTTPMiddleware`) keeps a single contextvar context across the whole
    stack and lets the `send` wrapper inject the header on any response.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _resolve_request_id(scope)
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        # The runtime's own context, not an API-owned one: `request_id` is one of the three run
        # identifiers it reserves, so every record emitted underneath carries it as an attribute.
        # The route path is deliberately not bound here — it is not a run identifier, and the API
        # ships it as a `url.path` field on the lines that want it (see `pipelex_api.exception_handlers`).
        with log.context(request_id=request_id):
            await self.app(scope, receive, send_with_request_id)
