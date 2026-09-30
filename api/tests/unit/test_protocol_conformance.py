"""MTHDS Protocol conformance gate — verifies this server against the normative spec.

Pipelex authors both the MTHDS Protocol spec (`mthds-protocol.openapi.yaml` in
the mthds repo) and this reference implementation, so this suite is the
mechanism that prevents first-party spec drift (master plan, eng review):

- The five protocol routes answer under `/v1/{execute,start,validate,models,version}`
  with the spec's status codes; no `/api/v1` mount or alias remains.
- `RunRequest` anyOf rule: a body with neither `pipe_code` nor `mthds_contents`
  is rejected with 422.
- `GET /version` is public (no auth) and returns the `VersionInfo` shape.
- A client-supplied `pipeline_run_id` on `/start` is honored (master D11 — this
  source-available runner accepts it; `StartAck.pipeline_run_id` echoes it back).
- The completion-callback E2E (eng-review 5A): `/start` with `callback_urls`
  delivers a signed POST to a local in-test receiver. The orchestrator is replaced
  by a fake whose `start` performs the real `DeliveryExecutor` delivery in-process, so
  the wire bytes (headers + JSON payload) are the production delivery path's.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from mthds.protocol.protocol import PROTOCOL_VERSION
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, DeliveryStatus
from pipelex.pipe_run.delivery_executor import DeliveryExecutor
from pipelex.pipeline.pipeline_response import RunState
from pipelex.runtime_bridge.payloads import PipelexPipeDispatchAck
from typing_extensions import override

from api.exception_handlers import register_exception_handlers
from api.routes import router as api_router
from api.routes.version import router as version_router
from api.security import verify_api_key
from tests.unit._constants import VALID_MTHDS

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

PROTOCOL_PATHS = {
    "/v1/execute": "POST",
    "/v1/start": "POST",
    "/v1/validate": "POST",
    "/v1/models": "GET",
    "/v1/version": "GET",
}


class _CallbackReceiver(BaseHTTPRequestHandler):
    """Minimal in-test HTTP receiver capturing completion-callback deliveries."""

    captured: ClassVar[list[dict[str, Any]]] = []

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        type(self).captured.append({"headers": dict(self.headers.items()), "body": body})
        self.send_response(200)
        self.end_headers()

    @override
    def log_message(self, format: str, *args: Any) -> None:
        """Silence per-request stderr logging."""


def _build_protocol_client(mocker: MockerFixture) -> TestClient:
    """A production-faithful `/v1` app with a mocked runner (no inference)."""
    app = FastAPI(redirect_slashes=False)
    app.include_router(version_router, prefix="/v1")
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)

    fake_execute_response = mocker.MagicMock()
    fake_execute_response.model_dump.return_value = {
        "pipeline_run_id": "conformance-run-1",
        "created_at": "2026-01-15T12:00:00Z",
        "state": "COMPLETED",
        "finished_at": "2026-01-15T12:00:01Z",
        "main_stuff_name": "main_stuff",
        "pipe_output": {"working_memory": {"root": {}, "aliases": {}}},
    }
    fake_runner = mocker.MagicMock()
    fake_runner.execute = mocker.AsyncMock(return_value=fake_execute_response)
    mocker.patch("api.routes.pipelex.pipeline.ApiRunner", return_value=fake_runner)
    return TestClient(app)


class TestProtocolConformance:
    def test_production_app_serves_protocol_paths_under_v1_only(self):
        """The production app mounts every protocol route under `/v1` — no `/api/v1`, no aliases."""
        from api.main import fastapi_app  # noqa: PLC0415 — imported in-test so a bad env var fails THIS test, not collection of the whole module

        served_paths = {route.path for route in fastapi_app.routes if isinstance(route, APIRoute)}
        for protocol_path in PROTOCOL_PATHS:
            assert protocol_path in served_paths, f"protocol route {protocol_path} is not served"
        legacy = [path for path in served_paths if path.startswith("/api/v1") or "/pipeline/" in path or "_version" in path]
        assert legacy == [], f"legacy paths must not be served: {legacy}"

    def test_version_is_public_and_protocol_shaped(self):
        """`GET /v1/version` answers WITHOUT credentials even when every other route requires auth."""
        app = FastAPI(redirect_slashes=False)
        # Mirror `api.main` wiring under AUTH_MODE=api_key: version mounts
        # outside the auth dependency, everything else inside it.
        app.include_router(version_router, prefix="/v1")
        app.include_router(api_router, prefix="/v1", dependencies=[Depends(verify_api_key)])
        register_exception_handlers(app)
        client = TestClient(app)

        # No Authorization header: the auth-gated surface rejects...
        assert client.get("/v1/models").status_code == 401
        # ...but the protocol handshake stays open.
        response = client.get("/v1/version")
        assert response.status_code == 200
        body = response.json()
        assert body["protocol_version"] == PROTOCOL_VERSION
        assert body["implementation"] == "pipelex-api"
        assert body["implementation_version"]
        assert body["runtime_version"]

    def test_validate_and_models_answer_200(self, mocker: MockerFixture):
        client = _build_protocol_client(mocker)
        validate_response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS]})
        assert validate_response.status_code == 200, validate_response.text
        models_response = client.get("/v1/models")
        assert models_response.status_code == 200, models_response.text

    def test_execute_answers_200(self, mocker: MockerFixture):
        client = _build_protocol_client(mocker)
        response = client.post(
            "/v1/execute",
            json={"pipe_code": "echo", "mthds_contents": [VALID_MTHDS], "inputs": {"text": "hi"}},
        )
        assert response.status_code == 200, response.text

    @pytest.mark.parametrize("path", ["/v1/execute", "/v1/start"])
    def test_run_request_anyof_rule_empty_body_is_422(self, mocker: MockerFixture, path: str):
        """Protocol `RunRequest`: at least one of pipe_code / mthds_contents is required."""
        client = _build_protocol_client(mocker)
        response = client.post(path, json={})
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"

    def test_start_accepts_client_pipeline_run_id_and_delivers_signed_callback(self, mocker: MockerFixture):
        """D11 + eng-review 5A: `/start` honors the client `pipeline_run_id`, answers 202,
        and the completion callback reaches the receiver with a valid
        `X-Completion-Signature` and a payload carrying the protocol `pipeline_run_id`.

        The orchestrator is replaced by a fake whose `start` immediately runs the REAL
        `DeliveryExecutor` delivery against the captured `DeliveryAssignment`
        (storage skipped — no pipe output), so headers and payload bytes come
        from the production delivery code path. The SSRF guards are relaxed for
        the loopback receiver: the request-time host check in
        `api.schemas.models` and the connect-time guarded transport in
        `pipelex.pipe_run.delivery_executor` both block loopback by design.
        """
        # --- local HTTP receiver -------------------------------------------------
        _CallbackReceiver.captured = []
        server = HTTPServer(("127.0.0.1", 0), _CallbackReceiver)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        callback_url = f"http://127.0.0.1:{server.server_port}/completion"

        # --- relax both SSRF layers for the loopback receiver (test-only) --------
        mocker.patch("api.schemas.models._is_disallowed_host", return_value=False)
        mocker.patch("pipelex.pipe_run.delivery_executor.SsrfGuardedTransport", httpx.AsyncHTTPTransport)

        # The signing secret is pinned HERE rather than relying on the ambient
        # env: `make agent-test` exports every `.env` key name (including
        # commented ones) into the child env as EMPTY strings, and
        # `os.environ.setdefault` in tests/conftest.py cannot replace an
        # existing empty value.
        test_secret = "conformance-shared-callback-secret"
        mocker.patch.dict(os.environ, {"COMPLETION_CALLBACK_SECRET": test_secret})

        # --- fake orchestrator: deliver the completion in-process -----------------
        # The runner now dispatches the locally-built PipeJob through the hub's
        # OrchestratorRegistry via its fire-and-forget `start` arm. Stand in a fake orchestrator
        # whose `start` performs the REAL DeliveryExecutor delivery and returns a
        # `PipelexPipeDispatchAck` (ids only, workflow_id set), so the delivery wire bytes still
        # come from the production path without needing a Temporal cluster or the
        # `pipelex-temporal` plugin.
        async def fake_start(*, pipe_job: Any, delivery_assignment: DeliveryAssignment) -> PipelexPipeDispatchAck:
            await DeliveryExecutor().execute(
                pipe_output=None,
                storage_scope="conformance-caller",
                pipeline_run_id=pipe_job.job_metadata.run_metadata.pipeline_run_id,
                delivery_assignment=delivery_assignment,
                status=DeliveryStatus.COMPLETED,
            )
            return PipelexPipeDispatchAck(
                pipeline_run_id=pipe_job.job_metadata.run_metadata.pipeline_run_id,
                workflow_id="wf-conformance-1",
            )

        # The fake stands in for an async-capable backend so `/start`'s capability gate passes (it
        # checks `supports_fire_and_forget` BEFORE dispatch — a blocking-only orchestrator would 400).
        fake_orchestrator = mocker.MagicMock()
        fake_orchestrator.supports_fire_and_forget = True
        fake_orchestrator.start = mocker.AsyncMock(side_effect=fake_start)
        fake_registry = mocker.MagicMock()
        fake_registry.get_optional.return_value = fake_orchestrator
        mocker.patch("api.routes.pipelex.pipeline.get_orchestrator_registry", return_value=fake_registry)

        app = FastAPI(redirect_slashes=False)
        app.include_router(api_router, prefix="/v1")
        register_exception_handlers(app)
        client = TestClient(app)

        client_pipeline_run_id = "conformance-client-run-0001"
        try:
            response = client.post(
                "/v1/start",
                json={
                    "pipe_code": "echo",
                    "mthds_contents": [VALID_MTHDS],
                    "inputs": {"text": "hello"},
                    "pipeline_run_id": client_pipeline_run_id,
                    "callback_urls": [callback_url],
                },
            )
        finally:
            server.shutdown()
            server_thread.join(timeout=5)
            server.server_close()

        # Protocol: 202 + StartAck; D11: the client-supplied pipeline_run_id is authoritative.
        assert response.status_code == 202, response.text
        ack = response.json()
        assert ack["pipeline_run_id"] == client_pipeline_run_id
        assert ack["state"] == RunState.STARTED

        # The runner resolved the deployment's orchestration mode and dispatched under it: with the
        # packaged-default config (`direct`) and no per-request override, the registry is asked for the
        # `direct` orchestrator by keyword `mode=` — so a regression that resolved/threaded the wrong
        # mode would be caught here, not silently dispatched.
        fake_registry.get_optional.assert_called_once_with(mode="direct")
        fake_orchestrator.start.assert_awaited_once()

        # Exactly one delivery reached the receiver.
        assert len(_CallbackReceiver.captured) == 1
        delivery = _CallbackReceiver.captured[0]

        # Signature: HMAC-SHA256(secret, pipeline_run_id) hex digest — the signing scheme
        # `_completion_signature` implements with the shared
        # COMPLETION_CALLBACK_SECRET.
        expected_signature = hmac.new(test_secret.encode("utf-8"), client_pipeline_run_id.encode("utf-8"), hashlib.sha256).hexdigest()
        assert delivery["headers"].get("X-Completion-Signature") == expected_signature

        # Payload: carries the protocol `pipeline_run_id` (static injection by ApiRunner)
        # plus the runtime's own delivery fields; `status` is a RunState value.
        payload = json.loads(delivery["body"])
        assert payload["pipeline_run_id"] == client_pipeline_run_id
        assert payload["pipeline_run_id"] == client_pipeline_run_id
        assert payload["status"] == RunState.COMPLETED
