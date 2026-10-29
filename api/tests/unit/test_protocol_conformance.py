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
- The webhook E2E: `/start` with `callback_urls` on a deployment with a completion
  target delivers, to a local in-test receiver, the signed `run.finished` event to the
  caller's URL and the completion notice, with its own signature, to the deployment's
  target, and never one hop's message or signature to the other. The orchestrator is
  replaced by a fake whose `start` performs the real `DeliveryExecutor` delivery
  in-process, so the wire bytes (headers + JSON body) are the production delivery path's.
"""

from __future__ import annotations

import base64
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
from pipelex.pipe_run.caller_webhook_delivery import CALLER_WEBHOOK_SECRET_ENV
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, DeliveryStatus
from pipelex.pipe_run.delivery_executor import DeliveryExecutor
from pipelex.pipeline.pipeline_response import RunState
from pipelex.runtime_bridge.payloads import PipelexPipeDispatchAck
from typing_extensions import override

from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router
from pipelex_api.routes.version import router as version_router
from pipelex_api.run_webhooks import COMPLETION_CALLBACK_URL_ENV
from pipelex_api.security import verify_api_key
from tests.unit._constants import VALID_MTHDS
from tests.unit.test_data import ProblemTestData

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
    """Minimal in-test HTTP receiver capturing webhook deliveries, by path."""

    captured: ClassVar[list[dict[str, Any]]] = []

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        type(self).captured.append({"path": self.path, "headers": {key.lower(): value for key, value in self.headers.items()}, "body": body})
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
    mocker.patch("pipelex_api.routes.pipelex.pipeline.ApiRunner", return_value=fake_runner)
    return TestClient(app)


class TestProtocolConformance:
    def test_production_app_serves_protocol_paths_under_v1_only(self):
        """The production app mounts every protocol route under `/v1` — no `/api/v1`, no aliases."""
        # Imported in-test so a bad env var fails THIS test, not collection of the whole module.
        from pipelex_api.main import fastapi_app  # noqa: PLC0415

        served_paths = {route.path for route in fastapi_app.routes if isinstance(route, APIRoute)}
        for protocol_path in PROTOCOL_PATHS:
            assert protocol_path in served_paths, f"protocol route {protocol_path} is not served"
        legacy = [path for path in served_paths if path.startswith("/api/v1") or "/pipeline/" in path or "_version" in path]
        assert legacy == [], f"legacy paths must not be served: {legacy}"

    def test_version_is_public_and_protocol_shaped(self):
        """`GET /v1/version` answers WITHOUT credentials even when every other route requires auth."""
        app = FastAPI(redirect_slashes=False)
        # Mirror `pipelex_api.main` wiring under AUTH_MODE=api_key: version mounts
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

    def test_start_delivers_the_caller_event_and_the_completion_notice_each_to_its_own_hop(self, mocker: MockerFixture):
        """`/start` honors the client `pipeline_run_id`, answers 202, and delivers two hops that never mix.

        The caller's URL receives the signed `run.finished` event (Standard Webhooks headers, verifiable under the caller
        secret) and no completion signature; the deployment's completion target, `COMPLETION_CALLBACK_URL`, receives the
        completion notice with its `X-Completion-Signature` and never the caller's event, and is notified once even though
        the host forwarded its URL among the `callback_urls`.

        The orchestrator is replaced by a fake whose `start` immediately runs the REAL `DeliveryExecutor` delivery against
        the captured `DeliveryAssignment` (storage skipped — no pipe output), so headers and body bytes come from the
        production delivery code path. The SSRF guards are relaxed for the loopback receiver: the request-time host check
        in `pipelex_api.schemas.models` and the connect-time guarded transports of both hops block loopback by design.
        """
        # --- local HTTP receiver -------------------------------------------------
        _CallbackReceiver.captured = []
        server = HTTPServer(("127.0.0.1", 0), _CallbackReceiver)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        receiver_base = f"http://127.0.0.1:{server.server_port}"
        caller_url = f"{receiver_base}/caller-hook"
        client_pipeline_run_id = "conformance-client-run-0001"
        completion_url = f"{receiver_base}/runs/complete/{client_pipeline_run_id}"

        # --- relax every SSRF layer for the loopback receiver (test-only) ---------
        mocker.patch("pipelex_api.schemas.models.is_disallowed_host", return_value=False)
        mocker.patch("pipelex.pipe_run.delivery_executor.SsrfGuardedTransport", httpx.AsyncHTTPTransport)
        mocker.patch("pipelex.pipe_run.caller_webhook_delivery.SsrfGuardedTransport", httpx.AsyncHTTPTransport)

        # The secrets are pinned HERE rather than relying on the ambient env: `make agent-test` exports every `.env` key
        # name (including commented ones) into the child env as EMPTY strings, and `os.environ.setdefault` in
        # tests/conftest.py cannot replace an existing empty value.
        completion_secret = "conformance-shared-callback-secret"
        mocker.patch.dict(
            os.environ,
            {
                "COMPLETION_CALLBACK_SECRET": completion_secret,
                COMPLETION_CALLBACK_URL_ENV: f"{receiver_base}/runs/complete/{{pipeline_run_id}}",
                CALLER_WEBHOOK_SECRET_ENV: ProblemTestData.SYNTHETIC_CALLER_WEBHOOK_SECRET,
            },
        )

        # --- fake orchestrator: deliver in-process --------------------------------
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

        # The fake stands in for an async-capable backend so `/start`'s capability gate passes (it checks
        # `supports_fire_and_forget` BEFORE dispatch — a blocking-only orchestrator would be refused).
        fake_orchestrator = mocker.MagicMock()
        fake_orchestrator.supports_fire_and_forget = True
        fake_orchestrator.start = mocker.AsyncMock(side_effect=fake_start)
        fake_registry = mocker.MagicMock()
        fake_registry.get_optional.return_value = fake_orchestrator
        mocker.patch("pipelex_api.routes.pipelex.pipeline.get_orchestrator_registry", return_value=fake_registry)

        app = FastAPI(redirect_slashes=False)
        app.include_router(api_router, prefix="/v1")
        register_exception_handlers(app)
        client = TestClient(app)

        try:
            response = client.post(
                "/v1/start",
                json={
                    "pipe_code": "echo",
                    "mthds_contents": [VALID_MTHDS],
                    "inputs": {"text": "hello"},
                    "pipeline_run_id": client_pipeline_run_id,
                    # The host forwards its own completion URL beside the caller's: it is the deployment's hop.
                    "callback_urls": [caller_url, completion_url],
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

        # One delivery per hop, the completion target notified once.
        deliveries = {delivery["path"]: delivery for delivery in _CallbackReceiver.captured}
        assert len(_CallbackReceiver.captured) == 2
        completion_delivery = deliveries[f"/runs/complete/{client_pipeline_run_id}"]
        caller_delivery = deliveries["/caller-hook"]

        # The completion target: HMAC-SHA256(secret, pipeline_run_id) hex digest, and the completion notice.
        expected_completion_signature = hmac.new(
            completion_secret.encode("utf-8"), client_pipeline_run_id.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        assert completion_delivery["headers"].get("x-completion-signature") == expected_completion_signature
        assert "webhook-signature" not in completion_delivery["headers"]
        notice = json.loads(completion_delivery["body"])
        assert notice["pipeline_run_id"] == client_pipeline_run_id
        assert notice["status"] == RunState.COMPLETED
        assert "type" not in notice

        # The caller's URL: the signed run.finished event, and never the completion signature.
        assert "x-completion-signature" not in caller_delivery["headers"]
        event = json.loads(caller_delivery["body"])
        assert event["type"] == "run.finished"
        assert event["attempt"] == 1
        assert event["data"] == {"pipeline_run_id": client_pipeline_run_id, "status": "completed"}
        headers = caller_delivery["headers"]
        assert headers["webhook-id"].startswith("whd_")
        signed_content = f"{headers['webhook-id']}.{headers['webhook-timestamp']}.".encode() + caller_delivery["body"]
        mac = hmac.new(ProblemTestData.SYNTHETIC_CALLER_WEBHOOK_KEY, signed_content, hashlib.sha256).digest()
        assert headers["webhook-signature"] == f"v1,{base64.b64encode(mac).decode('ascii')}"
