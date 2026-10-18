"""A caller holding its own token reads only under its own id, on every route that takes a `read_scope`.

With `AUTH_MODE=jwt` the caller reaches the runner directly, so the read scope it sends is its own claim, not a trusted
host's: a scope lying under another id is refused with a 403 `ReadScopeForbidden` before anything is read, whether the
route resolves hash entries in that scope's blob store, hands it to a validator or runs under it. On the other modes
the caller is the host or one tenant, so the same scope is taken as it is.
"""

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from mthds.method_tree.digest import sha256_hex
from pytest_mock import MockerFixture

from pipelex_api.api_config import ApiConfig
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router
from pipelex_api.routes.blob_upload import router as blob_upload_router
from pipelex_api.security import AUTH_MODE_ENV_VAR, RequestUser
from tests.unit._constants import VALID_MTHDS

_PIPELINE_NS = "pipelex_api.routes.pipelex.pipeline"
_CALLER_ID = "user_a"
_OTHER_ID = "user_b"
_BLOB = b"a file of the caller's method"


def _build_client(mocker: MockerFixture) -> TestClient:
    """An app whose every request is authenticated as `_CALLER_ID`, the shape `verify_jwt` binds."""
    mocker.patch(
        f"{_PIPELINE_NS}.get_api_config", return_value=ApiConfig(orchestration_mode="direct", allow_request_orchestration_mode_override=False)
    )
    app = FastAPI()

    async def _bind_user(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request.state.user = RequestUser(user_id=_CALLER_ID)
        return await call_next(request)

    app.middleware("http")(_bind_user)
    app.include_router(api_router, prefix="/v1")
    # The upload targets `/v1/blobs/missing` signs name this route.
    app.include_router(blob_upload_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


def _post(client: TestClient, *, route: str, read_scope: str) -> Any:
    """Each route taking a `read_scope`, sent the given one."""
    match route:
        case "/v1/blobs/missing":
            body: dict[str, Any] = {"blobs": [{"sha256": sha256_hex(_BLOB), "size": len(_BLOB)}]}
            return client.post(route, json=body, params={"read_scope": read_scope})
        case "/v1/validate-contents":
            return client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS], "read_scope": read_scope})
        case "/v1/validate" | "/v1/resolve" | "/v1/pipe-io":
            return client.post(route, json={"files": {"main.mthds": VALID_MTHDS}, "read_scope": read_scope})
        case "/v1/codegen":
            return client.post(route, json={"files": {"main.mthds": VALID_MTHDS}, "kind": "types", "target": "ts-zod", "read_scope": read_scope})
        case "/v1/execute":
            body = {"pipe_code": "echo", "files": {"main.mthds": VALID_MTHDS}, "inputs": {"text": "hello"}, "dry_run": True}
            return client.post(route, json={**body, "storage_scope": f"{read_scope}/run_1", "read_scope": read_scope})
        case _:
            msg = f"no request shape for {route}"
            raise AssertionError(msg)


_ROUTES = ["/v1/blobs/missing", "/v1/validate-contents", "/v1/validate", "/v1/resolve", "/v1/pipe-io", "/v1/codegen", "/v1/execute"]


class TestReadScopeBinding:
    @pytest.mark.parametrize("route", _ROUTES)
    @pytest.mark.parametrize("read_scope", [_OTHER_ID, f"{_OTHER_ID}/{_CALLER_ID}", f"{_CALLER_ID}x"])
    def test_a_jwt_caller_is_refused_a_scope_outside_its_own_id(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, route: str, read_scope: str
    ) -> None:
        monkeypatch.setenv(AUTH_MODE_ENV_VAR, "jwt")
        client = _build_client(mocker)

        response = _post(client, route=route, read_scope=read_scope)

        assert response.status_code == 403, response.text
        assert response.headers["content-type"] == "application/problem+json"
        problem = response.json()
        assert problem["error_type"] == "ReadScopeForbidden", response.text
        assert repr(read_scope) in problem["detail"]

    @pytest.mark.parametrize("route", _ROUTES)
    @pytest.mark.parametrize("read_scope", [_CALLER_ID, f"{_CALLER_ID}/org_x"])
    def test_a_jwt_caller_reads_under_its_own_id(self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, route: str, read_scope: str) -> None:
        monkeypatch.setenv(AUTH_MODE_ENV_VAR, "jwt")
        client = _build_client(mocker)

        response = _post(client, route=route, read_scope=read_scope)

        assert response.status_code == 200, response.text

    @pytest.mark.parametrize("route", _ROUTES)
    @pytest.mark.parametrize("auth_mode", ["none", "api_key"])
    def test_a_host_or_a_single_tenant_names_any_scope(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, route: str, auth_mode: str
    ) -> None:
        """A trusted host sends the organization it serves, which lies under no user's id."""
        monkeypatch.setenv(AUTH_MODE_ENV_VAR, auth_mode)
        client = _build_client(mocker)

        response = _post(client, route=route, read_scope=_OTHER_ID)

        assert response.status_code == 200, response.text
