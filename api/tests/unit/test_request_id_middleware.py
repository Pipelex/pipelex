"""Unit tests for RequestIdMiddleware and request-id propagation."""

import logging
import re
import time

import pytest
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from pipelex import log
from pipelex.tools.log.log_context import get_log_context
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import Message, Receive, Scope, Send

from api.middleware import REQUEST_ID_HEADER, RequestIdMiddleware, generate_request_id, request_body_size_middleware, request_id_of

# Crockford Base32, 26 chars — the ULID alphabet (no I, L, O, U).
_ULID_RE = re.compile(r"\A[0-9A-HJKMNP-TV-Z]{26}\Z")

# The message the `/emits-a-log-line` route logs, matched back out of the captured records.
_ROUTE_LOG_MESSAGE = "a line emitted from inside the request"

_router = APIRouter()


@_router.get("/probe")
async def probe(request: Request) -> dict[str, str | None]:
    bound = get_log_context()
    return {
        "ctx_request_id": bound.request_id if bound is not None else None,
        "state_request_id": request.state.request_id,
        "helper_request_id": request_id_of(request),
    }


@_router.get("/emits-a-log-line")
async def emits_a_log_line() -> dict[str, str]:
    log.warning(_ROUTE_LOG_MESSAGE)
    return {"status": "logged"}


@_router.get("/boom")
async def boom() -> None:
    raise HTTPException(status_code=400, detail="deliberate")


@_router.get("/explode")
async def explode() -> None:
    msg = "deliberate unhandled error"
    raise RuntimeError(msg)


def _build_client(*, raise_server_exceptions: bool = True) -> TestClient:
    """Build a client over the production middleware composition.

    `RequestIdMiddleware` wraps a FastAPI app that itself carries the body-size
    `BaseHTTPMiddleware` — mirroring `api.main`, so the tests exercise contextvar
    survival across the `BaseHTTPMiddleware` child-task boundary and the
    catch-all 500 emitted by Starlette's `ServerErrorMiddleware`.
    """
    inner = FastAPI()
    inner.add_middleware(BaseHTTPMiddleware, dispatch=request_body_size_middleware)
    inner.include_router(_router)
    return TestClient(RequestIdMiddleware(inner), raise_server_exceptions=raise_server_exceptions)


class TestRequestIdMiddleware:
    def test_generates_ulid_when_absent(self):
        response = _build_client().get("/probe")
        assert response.status_code == 200
        request_id = response.headers[REQUEST_ID_HEADER]
        assert _ULID_RE.match(request_id) is not None
        body = response.json()
        assert body["ctx_request_id"] == request_id
        assert body["state_request_id"] == request_id
        assert body["helper_request_id"] == request_id

    def test_bound_context_puts_the_request_id_on_every_record(self, caplog: pytest.LogCaptureFixture):
        # The middleware binds the runtime's own log context for the request, so a record emitted
        # anywhere underneath — a route's own line here, but equally one from deep inside pipelex —
        # carries `request_id` as a record attribute. The runner no longer interpolates the id into
        # a message, which is what makes the id a field a structured sink indexes.
        with caplog.at_level(logging.WARNING):
            response = _build_client().get("/emits-a-log-line")
        assert response.status_code == 200
        request_id = response.headers[REQUEST_ID_HEADER]
        emitted = [record for record in caplog.records if record.getMessage() == _ROUTE_LOG_MESSAGE]
        assert len(emitted) == 1, f"expected exactly one captured record, got {[record.getMessage() for record in caplog.records]}"
        assert getattr(emitted[0], "request_id", None) == request_id
        # The id rides the record, never the message — a sink indexes the field, and an operator
        # grepping the text of a line is not the contract any more.
        assert request_id not in emitted[0].getMessage()

    @pytest.mark.asyncio
    async def test_bound_context_is_released_when_the_request_ends(self):
        # The binding is per-request: once the request is over, nothing emitted afterwards may inherit
        # its id, or a shared worker would attribute later work to it. The middleware is driven on this
        # test's own event loop rather than through `TestClient`, which runs the app in a portal thread
        # whose context never reaches the test's — through it, a binding that leaked would look released.
        bound_while_running: list[str | None] = []

        async def inner(_scope: Scope, _receive: Receive, send: Send) -> None:
            bound = get_log_context()
            bound_while_running.append(bound.request_id if bound is not None else None)
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        async def receive() -> Message:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: Message) -> None:
            pass

        scope: Scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
        assert get_log_context() is None
        await RequestIdMiddleware(inner)(scope, receive, send)

        assert len(bound_while_running) == 1
        assert bound_while_running[0] is not None, "the id must be bound while the request runs"
        assert get_log_context() is None, "the binding outlived the request"

    def test_echoes_valid_inbound_id(self):
        response = _build_client().get("/probe", headers={REQUEST_ID_HEADER: "client-supplied-123"})
        assert response.headers[REQUEST_ID_HEADER] == "client-supplied-123"
        assert response.json()["ctx_request_id"] == "client-supplied-123"

    def test_replaces_malformed_inbound_id(self):
        response = _build_client().get("/probe", headers={REQUEST_ID_HEADER: "bad id with spaces"})
        returned = response.headers[REQUEST_ID_HEADER]
        assert returned != "bad id with spaces"
        assert _ULID_RE.match(returned) is not None

    def test_replaces_overlong_inbound_id(self):
        overlong = "a" * 200
        response = _build_client().get("/probe", headers={REQUEST_ID_HEADER: overlong})
        returned = response.headers[REQUEST_ID_HEADER]
        assert returned != overlong
        assert _ULID_RE.match(returned) is not None

    def test_header_present_on_handled_error_response(self):
        response = _build_client().get("/boom")
        assert response.status_code == 400
        assert _ULID_RE.match(response.headers[REQUEST_ID_HEADER]) is not None

    def test_header_present_on_unhandled_500(self):
        # Because RequestIdMiddleware wraps the whole app, even the 500 that
        # Starlette's ServerErrorMiddleware emits flows through the send wrapper.
        response = _build_client(raise_server_exceptions=False).get("/explode")
        assert response.status_code == 500
        assert _ULID_RE.match(response.headers[REQUEST_ID_HEADER]) is not None

    def test_generate_request_id_is_unique(self):
        first = generate_request_id()
        second = generate_request_id()
        assert first != second
        assert len(first) == 26
        assert _ULID_RE.match(first) is not None

    def test_generate_request_id_is_time_sortable(self):
        # The ULID's high 48 bits are a millisecond timestamp and Crockford
        # Base32 is ASCII-ascending, so ids minted across a time gap sort
        # lexicographically — the property that makes ULID preferable to UUIDv4.
        first = generate_request_id()
        time.sleep(0.002)
        second = generate_request_id()
        assert first < second
