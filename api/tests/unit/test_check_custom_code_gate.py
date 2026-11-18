"""`scripts/check_custom_code_gate.py` passes only a server that refuses a method shipping Python with the custom-code 501.

`make docker-smoke` runs it against the booted image, so it is what notices a drift in the config the image ships
opening the gate. The request it sends is checked against the server's own routes, behind the production handlers,
with the gate closed and then open, so the script cannot drift from the route it probes; its other verdicts are
checked one defect at a time; and one end-to-end run reads a refusal from a stub server over HTTP, as it does from the
container. The script is a standalone entry point, not a package module, so it is loaded from its path.
"""

import importlib.util
import json
import sys
import threading
from collections.abc import Generator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex_api.api_config import ApiConfig
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router

_MEMBER_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _MEMBER_ROOT / "scripts" / "check_custom_code_gate.py"
_PIPELINE_NS = "pipelex_api.routes.pipelex.pipeline"
_TREE_NS = "pipelex_api.method_tree_request"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_custom_code_gate", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_custom_code_gate = _load_script()

_REFUSAL: dict[str, Any] = {
    "type": "https://docs.pipelex.com/errors/pipelex.deployment.custom_code_requires_sandbox",
    "status": 501,
    **check_custom_code_gate.EXPECTED_PROBLEM,
}


def _build_client(mocker: MockerFixture) -> TestClient:
    mocker.patch(
        f"{_PIPELINE_NS}.get_api_config", return_value=ApiConfig(orchestration_mode="direct", allow_request_orchestration_mode_override=False)
    )
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


class TestTheProbeAgainstTheRoutes:
    def test_a_server_whose_gate_is_closed_passes(self, mocker: MockerFixture) -> None:
        mocker.patch(f"{_TREE_NS}.is_pipe_func_sandbox_hosted", return_value=False)
        client = _build_client(mocker)

        response = client.post("/v1/validate", json=check_custom_code_gate.REQUEST_BODY)

        assert check_custom_code_gate.refusal_mismatch(status=response.status_code, body=response.json()) is None, response.text

    def test_a_server_whose_gate_is_open_fails(self, mocker: MockerFixture) -> None:
        mocker.patch(f"{_TREE_NS}.is_pipe_func_sandbox_hosted", return_value=True)
        client = _build_client(mocker)

        response = client.post("/v1/validate", json=check_custom_code_gate.REQUEST_BODY)

        assert check_custom_code_gate.refusal_mismatch(status=response.status_code, body=response.json()) is not None, response.text


class TestTheVerdict:
    def test_the_custom_code_refusal_passes(self) -> None:
        assert check_custom_code_gate.refusal_mismatch(status=501, body=_REFUSAL) is None

    @pytest.mark.parametrize(
        ("status", "body", "named"),
        [
            pytest.param(200, {"is_valid": True}, "status 501", id="accepted"),
            pytest.param(422, {**_REFUSAL, "status": 422}, "status 501", id="another-status"),
            pytest.param(501, "Not Implemented", "JSON problem", id="not-a-problem"),
            pytest.param(501, {**_REFUSAL, "code": "runtime.unexpected"}, "'code'", id="another-code"),
            pytest.param(501, {**_REFUSAL, "domain": "runtime"}, "'domain'", id="another-domain"),
            pytest.param(501, {**_REFUSAL, "params": {"origin": "method_ref"}}, "'params'", id="another-origin"),
            pytest.param(501, {key: value for key, value in _REFUSAL.items() if key != "params"}, "'params'", id="no-params"),
        ],
    )
    def test_any_other_answer_fails_and_says_why(self, status: int, body: Any, named: str) -> None:
        mismatch = check_custom_code_gate.refusal_mismatch(status=status, body=body)

        assert mismatch is not None
        assert named in mismatch


class _StubHandler(BaseHTTPRequestHandler):
    status: ClassVar[int] = 501
    body: ClassVar[dict[str, Any]] = _REFUSAL
    received: ClassVar[list[Any]] = []

    def do_POST(self) -> None:
        length = int(self.headers["content-length"])
        self.received.append((self.path, json.loads(self.rfile.read(length))))
        payload = json.dumps(self.body).encode("utf-8")
        self.send_response(self.status)
        self.send_header("content-type", "application/problem+json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    @override
    def log_message(self, format: str, *args: Any) -> None:
        """Keep the stub's request log out of the test output."""


@pytest.fixture
def stub_server() -> Generator[str, None, None]:
    _StubHandler.received.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


class TestTheScriptOverHttp:
    def test_it_reads_the_refusal_from_an_error_status(self, stub_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["check_custom_code_gate.py", stub_server])

        exit_code = check_custom_code_gate.main()

        assert exit_code == 0
        assert _StubHandler.received == [("/v1/validate", check_custom_code_gate.REQUEST_BODY)]

    def test_it_fails_on_an_accepted_method(self, stub_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_StubHandler, "status", 200)
        monkeypatch.setattr(_StubHandler, "body", {"is_valid": True})
        monkeypatch.setattr(sys, "argv", ["check_custom_code_gate.py", stub_server])

        assert check_custom_code_gate.main() == 1
