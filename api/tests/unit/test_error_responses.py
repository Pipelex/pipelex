"""Phase 3 regression tests — every API error path emits one RFC 7807 shape.

Builds a production-faithful app (the real routers, the global exception
handlers, `RequestIdMiddleware`, the body-size middleware) and asserts that
4xx/5xx responses across the surface are `application/problem+json` with the
RFC 7807 fields and an `X-Request-ID` header — never the old
`{"detail": {...}}` envelope, and never FastAPI's default `{"detail": [...]}`
for automatic request validation. Covers regression checks T1 (413), T2
(a route-level 403) and T5 (`X-Request-ID` on every error response).

The 400/403/401 vehicles used to be the storage and upload routes. Those moved
to the hosted platform, so each assertion now rides a different route that
raises through the same helper — the envelope is what is under test, never the
route that produced it.
"""

from collections.abc import Iterator
from importlib.metadata import PackageNotFoundError

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture
from starlette.middleware.base import BaseHTTPMiddleware

from api.exception_handlers import register_exception_handlers
from api.middleware import REQUEST_ID_HEADER, RequestIdMiddleware, request_body_size_middleware
from api.problem_document import PROBLEM_JSON_MEDIA_TYPE
from api.routes import router as api_router
from api.routes.version import router as version_router
from api.security import RequestUser, get_request_user, verify_api_key

USER_A = "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa"
USER_B = "bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb"
FILE_HASH = "cccccccc-cccc-4ccc-cccc-cccccccccccc"


def _build_client(*, user: RequestUser | None = None, with_auth: bool = False) -> TestClient:
    """Wire a production-faithful app: real routers, handlers, both middlewares.

    `RequestIdMiddleware` wraps the whole app exactly as in `api.main`, so the
    request-id contextvars are bound and `X-Request-ID` is stamped on every
    response. `get_request_user` is overridden so routes see the caller
    identity the test wants.

    `with_auth` mounts the composite router behind the SAME `auth_dependency`
    `api.main` uses, which is the only way to reach a real 401 — every
    `raise_unauthenticated` lives in the verifiers that dependency runs, not in
    a route body.
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
    return TestClient(RequestIdMiddleware(app))


class TestErrorResponses:
    def test_validation_error_is_rfc7807_input_domain(self):
        # /models with an unknown category → raise_validation_error → 422.
        response = _build_client().get("/v1/models?type=not-a-real-category")
        assert response.status_code == 422
        assert response.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
        body = response.json()
        assert body["error_type"] == "InvalidModelCategory"
        assert body["error_domain"] == "input"
        assert body["instance"] == "/v1/models"
        assert body["status"] == 422
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]
        # API-authored caller-input errors are non-retryable across the surface.
        assert body["retryable"] is False

    def test_request_validation_error_is_rfc7807(self):
        # FastAPI's automatic body validation (here: mthds_contents below its
        # min_length) must answer in the same RFC 7807 shape as every other
        # path — not FastAPI's default {"detail": [...]} / application/json.
        response = _build_client().post("/v1/validate", json={"mthds_contents": []})
        assert response.status_code == 422
        assert response.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
        body = response.json()
        assert body["error_type"] == "ValidationError"
        assert body["error_domain"] == "input"
        assert body["status"] == 422
        assert body["instance"] == "/v1/validate"
        assert isinstance(body["detail"], str)
        assert "mthds_contents" in body["detail"]
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]
        assert body["retryable"] is False

    def test_bad_request_is_rfc7807(self):
        # A `bundle_b64` that is not valid base64 → raise_bad_request → 400.
        client = _build_client(user=RequestUser(user_id=USER_A))
        response = client.post("/v1/execute", json={"bundle_b64": "not!base64", "pipe_code": "smoke"})
        assert response.status_code == 400
        assert response.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
        body = response.json()
        assert body["error_type"] == "InvalidBase64"
        assert body["error_domain"] == "input"
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]
        assert body["retryable"] is False

    def test_forbidden_is_rfc7807(self):
        # REGRESSION T2: a per-request orchestration-mode override the
        # deployment forbids → raise_forbidden → 403.
        client = _build_client(user=RequestUser(user_id=USER_A))
        response = client.post(
            "/v1/execute",
            json={"mthds_contents": ['domain = "smoke"'], "pipe_code": "smoke", "orchestration_mode": "definitely-not-the-default"},
        )
        assert response.status_code == 403
        assert response.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
        body = response.json()
        assert body["error_type"] == "OrchestrationModeOverrideForbidden"
        assert body["status"] == 403
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]
        assert body["retryable"] is False

    def test_payload_too_large_is_rfc7807(self):
        # REGRESSION T1: a body over the cap → 413 via the body-size middleware.
        response = _build_client().get(
            "/v1/version",
            headers={"content-length": str(200 * 1024 * 1024)},
        )
        assert response.status_code == 413
        assert response.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
        body = response.json()
        assert body["error_type"] == "PayloadTooLarge"
        assert body["error_domain"] == "input"
        assert body["status"] == 413
        # The body-size middleware has to return a response rather than raise, so it builds its own
        # problem document — and it reads the route and the id off the `Request` it was handed,
        # like every other error path.
        assert body["instance"] == "/v1/version"
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]
        assert body["retryable"] is False

    def test_payload_too_large_chunked_does_not_buffer_oversized_body(self, mocker: MockerFixture):
        # REGRESSION T1b: a chunked / no-content-length over-limit body must reject
        # before the route can buffer or process it. Without the fix, the middleware
        # only flips `too_large` after `call_next` returns, leaving the route free to
        # fully `await request.body()` on the oversized stream — defeating memory/CPU
        # protection and allowing route side effects to run before the 413.
        mocker.patch("api.middleware.MAX_REQUEST_BODY_BYTES", 1024)

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

        assert response.status_code == 413
        assert response.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
        assert response.json()["error_type"] == "PayloadTooLarge"
        # With the fix, the over-limit first chunk is replaced with an end-of-stream
        # marker, so the route observes an empty body. Without the fix, the route
        # would see all 4096 bytes.
        assert bytes_seen_by_route == [0]

    def test_internal_server_error_is_rfc7807_config_domain(self, mocker: MockerFixture):
        # Absent package metadata → raise_internal_server_error → 500 CONFIG.
        mocker.patch("api.routes.version.version", side_effect=PackageNotFoundError("pipelex"))
        response = _build_client().get("/v1/version")
        assert response.status_code == 500
        assert response.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
        body = response.json()
        assert body["error_type"] == "PackageNotFound"
        assert body["error_domain"] == "config"
        assert body["status"] == 500
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]
        # An API-owned 5xx is non-retryable: the operator, not the caller,
        # fixes a missing package; the symmetry with the 4xx paths is the
        # uniform retry contract clients can rely on.
        assert body["retryable"] is False

    def test_unauthenticated_carries_www_authenticate_challenge(self):
        # No Authorization header on an auth-wrapped route → 401 + challenge.
        response = _build_client(user=None, with_auth=True).post("/v1/validate", json={"mthds_contents": ['domain = "smoke"']})
        assert response.status_code == 401
        assert response.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
        assert response.headers["WWW-Authenticate"] == "Bearer"
        body = response.json()
        assert body["error_type"] == "Unauthenticated"
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]
        assert body["retryable"] is False

    def test_inbound_request_id_is_echoed_into_error_body(self):
        # A caller-supplied X-Request-ID rides through to the response body.
        response = _build_client().get(
            "/v1/models?type=not-a-real-category",
            headers={REQUEST_ID_HEADER: "inbound-correlation-303"},
        )
        assert response.status_code == 422
        assert response.headers[REQUEST_ID_HEADER] == "inbound-correlation-303"
        assert response.json()["request_id"] == "inbound-correlation-303"
