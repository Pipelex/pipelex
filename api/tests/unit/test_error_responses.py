"""Every error path of the runner answers one shape: the problem document of a registry code.

Builds a production-faithful app (the real routers, the global exception handlers, `RequestIdMiddleware`, the body-size
middleware) and asserts that 4xx and 5xx responses across the surface are `application/problem+json` carrying a code,
the status that code declares, the request's id, which also rides the `X-Request-ID` header, and no `instance` — never
the old `{"detail": {...}}` envelope, and never FastAPI's default `{"detail": [...]}` for automatic request validation.
The envelope is what is under test, never the route that produced it.
"""

import json
from collections.abc import Iterator
from importlib.metadata import PackageNotFoundError

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture
from starlette.middleware.base import BaseHTTPMiddleware

from pipelex_api import json_body
from pipelex_api.exception_handlers import AnsweredErrorBarrier, register_exception_handlers
from pipelex_api.limits import MAX_REQUEST_BODY_BYTES
from pipelex_api.middleware import REQUEST_ID_HEADER, RequestIdMiddleware, request_body_size_middleware
from pipelex_api.routes import router as api_router
from pipelex_api.routes.version import router as version_router
from pipelex_api.security import RequestUser, get_request_user, verify_api_key
from tests.unit._problems import assert_problem, problem_items_fields

USER_A = "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa"
USER_B = "bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb"
FILE_HASH = "cccccccc-cccc-4ccc-cccc-cccccccccccc"


def _build_client(*, user: RequestUser | None = None, with_auth: bool = False) -> TestClient:
    """Wire a production-faithful app: real routers, handlers, both middlewares.

    `RequestIdMiddleware` wraps the whole app, through `AnsweredErrorBarrier`, exactly as
    in `pipelex_api.main`, so the request-id contextvars are bound and `X-Request-ID` is
    stamped on every response. `get_request_user` is overridden so routes see the caller
    identity the test wants.

    `with_auth` mounts the composite router behind an authentication dependency
    `pipelex_api.main` can select, the API key's verifier, which is the only way to reach
    a real 401: every authentication refusal, a `RunnerAuthError`, is raised by the
    verifier that dependency runs, not in a route body.
    """
    app = FastAPI(redirect_slashes=False)
    app.add_middleware(BaseHTTPMiddleware, dispatch=request_body_size_middleware)
    app.include_router(version_router, prefix="/v1")
    if with_auth:
        app.include_router(api_router, prefix="/v1", dependencies=[Depends(verify_api_key)])
    else:
        app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)

    async def _override_user() -> RequestUser | None:
        return user

    app.dependency_overrides[get_request_user] = _override_user
    return TestClient(RequestIdMiddleware(AnsweredErrorBarrier(app)))


class TestErrorResponses:
    def test_a_refused_field_is_a_request_invalid_problem_in_the_input_domain(self):
        # /models with an unknown category: the runner refuses the field itself.
        response = _build_client().get("/v1/models?type=not-a-real-category")
        body = assert_problem(response, status=422, code="request.invalid", field="type")
        assert body["domain"] == "input"
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]
        # A caller's mistake is not retried as it is.
        assert body["retry"] == "no"

    def test_a_body_the_route_model_refuses_is_the_same_problem(self):
        # FastAPI's automatic body validation (here: mthds_contents below its min_length) answers in the same shape as
        # every other path — not FastAPI's default {"detail": [...]} / application/json.
        response = _build_client().post("/v1/validate", json={"mthds_contents": []})
        body = assert_problem(response, status=422, code="request.invalid", field="mthds_contents")
        assert body["domain"] == "input"
        assert body["detail"] == "The request's field 'mthds_contents' does not match the route's schema."
        assert problem_items_fields(body) == ["mthds_contents"]
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]
        assert body["retry"] == "no"

    def test_an_encoded_part_that_cannot_be_decoded_is_a_malformed_request(self):
        # A `bundle_b64` that is not valid base64: the request cannot be read, a 422 like every caller's mistake.
        client = _build_client(user=RequestUser(user_id=USER_A))
        response = client.post("/v1/execute", json={"bundle_b64": "not!base64", "pipe_code": "smoke"})
        body = assert_problem(response, status=422, code="request.malformed")
        assert body["params"] == {"reason": "bad_base64"}
        assert body["domain"] == "input"
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]
        assert body["retry"] == "no"

    def test_a_deployment_policy_refusal_is_its_own_code(self):
        # A per-request orchestration-mode override the deployment forbids: the request is the caller's to change.
        client = _build_client(user=RequestUser(user_id=USER_A))
        response = client.post(
            "/v1/execute",
            json={"mthds_contents": ['domain = "smoke"'], "pipe_code": "smoke", "orchestration_mode": "definitely-not-the-default"},
        )
        body = assert_problem(response, status=422, code="pipelex.deployment.orchestration_override_forbidden")
        assert body["params"] == {"requested_mode": "definitely-not-the-default"}
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]
        assert body["retry"] == "no"

    def test_a_body_past_the_size_limit_is_a_too_large_problem(self):
        # A declared body over the cap: a 413 from the body-size middleware, before any route runs.
        response = _build_client().get(
            "/v1/version",
            headers={"content-length": str(200 * 1024 * 1024)},
        )
        body = assert_problem(response, status=413, code="request.too_large")
        assert body["params"] == {"limit": MAX_REQUEST_BODY_BYTES, "size": 200 * 1024 * 1024}
        assert body["domain"] == "input"
        # The body-size middleware has to return a response rather than raise, so it renders the problem itself, and it
        # reads the request's id off the `Request` it was handed, like every other error path.
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]
        assert body["retry"] == "no"

    def test_payload_too_large_chunked_does_not_buffer_oversized_body(self, mocker: MockerFixture):
        # REGRESSION T1b: a chunked / no-content-length over-limit body must reject
        # before the route can buffer or process it. Without the fix, the middleware
        # only flips `too_large` after `call_next` returns, leaving the route free to
        # fully `await request.body()` on the oversized stream — defeating memory/CPU
        # protection and allowing route side effects to run before the 413.
        mocker.patch("pipelex_api.middleware.MAX_REQUEST_BODY_BYTES", 1024)

        bytes_seen_by_route: list[int] = []

        async def echo(request: Request) -> JSONResponse:
            body = await request.body()
            bytes_seen_by_route.append(len(body))
            return JSONResponse({"length": len(body)})

        app = FastAPI(redirect_slashes=False)
        app.add_middleware(BaseHTTPMiddleware, dispatch=request_body_size_middleware)
        app.add_api_route("/echo", echo, methods=["POST"])
        register_exception_handlers(app)

        client = TestClient(RequestIdMiddleware(app))

        # 4 KiB body, 4x the patched 1 KiB cap. A generator forces httpx to use
        # chunked transfer encoding, exercising the counting branch instead of
        # the fast Content-Length reject.
        def streaming_body() -> Iterator[bytes]:
            yield b"x" * 4096

        response = client.post("/echo", content=streaming_body())

        body = assert_problem(response, status=413, code="request.too_large")
        # A body streamed without a declared length is refused at the first chunk past the limit, which is all it read.
        assert body["params"]["limit"] == 1024
        # With the fix, the over-limit first chunk is replaced with an end-of-stream
        # marker, so the route observes an empty body. Without the fix, the route
        # would see all 4096 bytes.
        assert bytes_seen_by_route == [0]

    def test_a_typed_route_reads_its_body_through_the_size_limit(self, mocker: MockerFixture):
        # `JsonBodyRoute` reads a typed body itself, before FastAPI: it must read it through the body-size middleware's
        # counting `receive`, once, so a body streamed past the limit is refused as too large rather than parsed.
        mocker.patch("pipelex_api.middleware.MAX_REQUEST_BODY_BYTES", 1024)
        parse_spy = mocker.spy(json_body, "parse_typed_json_body")
        runner_spy = mocker.patch("pipelex_api.routes.pipelex.validate.ApiRunner")
        over_limit = json.dumps({"mthds_contents": ["x" * 4096]}).encode("utf-8")

        def streaming_body() -> Iterator[bytes]:
            yield over_limit

        response = _build_client().post("/v1/validate", content=streaming_body(), headers={"content-type": "application/json"})

        body = assert_problem(response, status=413, code="request.too_large")
        assert body["params"] == {"limit": 1024, "size": len(over_limit)}
        # The route read the end of stream the middleware put in place of the over-limit chunk, never the body itself.
        parse_spy.assert_not_called()
        runner_spy.assert_not_called()

    def test_a_typed_route_reads_a_body_within_the_limit_once(self, mocker: MockerFixture):
        # The same route reading the same middleware's `receive` gets the whole body when it is within the limit, and
        # FastAPI validates the value the route parsed, reading the body no second time.
        mocker.patch("pipelex_api.middleware.MAX_REQUEST_BODY_BYTES", 1024)
        parse_spy = mocker.spy(json_body, "parse_typed_json_body")

        def streaming_body() -> Iterator[bytes]:
            yield b'{"mthds_contents": []}'

        response = _build_client().post("/v1/validate", content=streaming_body(), headers={"content-type": "application/json"})

        # An empty list is refused by the route's model, which proves the model read the parsed body.
        assert_problem(response, status=422, code="request.invalid")
        assert parse_spy.call_count == 1

    def test_a_misconfigured_runner_is_a_runtime_problem(self, mocker: MockerFixture):
        # Absent package metadata: the installation, not the request, is at fault.
        mocker.patch("pipelex_api.routes.version.version", side_effect=PackageNotFoundError("pipelex"))
        response = _build_client().get("/v1/version")
        body = assert_problem(response, status=500, code="runtime.misconfigured")
        assert body["domain"] == "operator"
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]
        # The operator, not the caller, fixes a missing package, so the caller does not retry it.
        assert body["retry"] == "no"
        # Which component is misconfigured is the operator's to read, never the caller's.
        assert "params" not in body
        assert "diagnostics" not in body

    def test_unauthenticated_carries_www_authenticate_challenge(self):
        # No Authorization header on an auth-wrapped route → 401 + challenge.
        response = _build_client(user=None, with_auth=True).post("/v1/validate", json={"mthds_contents": ['domain = "smoke"']})
        body = assert_problem(response, status=401, code="auth.missing_credential")
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]
        assert body["retry"] == "no"

    def test_inbound_request_id_is_echoed_into_error_body(self):
        # A caller-supplied X-Request-ID rides through to the response body.
        response = _build_client().get(
            "/v1/models?type=not-a-real-category",
            headers={REQUEST_ID_HEADER: "inbound-correlation-303"},
        )
        assert response.status_code == 422
        assert response.headers[REQUEST_ID_HEADER] == "inbound-correlation-303"
        assert response.json()["request_id"] == "inbound-correlation-303"
