"""A sandbox-hosted deployment refuses a bundle whose Python declares a structure class, and never imports it.

The run routes load the bundle for real here: only the orchestrator is a recording stub, so the refusal
is the runtime's own, raised while the bundle loads. A module-level sentinel in the structure file proves
the file was never imported, which is the point of the refusal: hosted execution imports no caller Python
into the runner's process. A PipeFunc-only bundle passes the same load and reaches the orchestrator.
"""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipelex.base_exceptions import DisclosureMode
from pipelex.config import get_config
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.plugins.orchestrator_registry import OrchestratorRegistry
from pipelex.runtime_bridge.payloads import PipelexPipeDispatchAck, PipelexPipeRunOutput
from pytest_mock import MockerFixture

from pipelex_api.api_config import ApiConfig
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router
from tests.unit._constants import VALID_MTHDS

_PIPELINE_NS = "pipelex_api.routes.pipelex.pipeline"

_PIPE_FUNC_MTHDS = """\
domain = "crunch_demo"
main_pipe = "crunch"

[pipe.crunch]
type = "PipeFunc"
description = "Crunch numbers in caller code"
inputs = { data = "Text" }
output = "Text"
function_name = "crunch"
"""

_PIPE_FUNC_PY = """\
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func


@pipe_func(name="crunch")
async def crunch(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text="crunched")
"""


def _structures_py(*, sentinel: Path) -> str:
    """A structure class whose module, if it were ever imported, would write the sentinel file."""
    return f"""\
from pathlib import Path

from pipelex.core.stuffs.structured_content import StructuredContent

Path({str(sentinel)!r}).write_text("imported", encoding="utf-8")


class Invoice(StructuredContent):
    total: float
"""


class _RecordingOrchestrator:
    """Records every dispatch; `start` acknowledges it, `execute` is never expected to be reached."""

    supports_fire_and_forget = True

    def __init__(self) -> None:
        self.dispatches: list[str] = []

    async def execute(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeRunOutput:  # noqa: ARG002
        self.dispatches.append(pipe_job.pipe.code)
        msg = "These tests dispatch through /start only."
        raise AssertionError(msg)

    async def start(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeDispatchAck:  # noqa: ARG002
        self.dispatches.append(pipe_job.pipe.code)
        return PipelexPipeDispatchAck(pipeline_run_id="run-1", workflow_id="wf-1")


@pytest.fixture(name="sandbox_hosted_mode")
def sandbox_hosted_mode_fixture() -> Generator[None, None, None]:
    """Select a non-`direct` PipeFunc execution mode, which is what makes a deployment sandbox-hosted.

    Flipping the config rather than patching a helper makes the route's gate and pipelex's loader read
    the same answer. The token is neutral: no sandbox plugin is installed, and nothing here runs a PipeFunc.
    """
    pipe_func_config = get_config().interpreter.pipe_func
    previous = pipe_func_config.execution_mode
    pipe_func_config.execution_mode = "sandbox"
    try:
        yield
    finally:
        pipe_func_config.execution_mode = previous


def _build_client(mocker: MockerFixture, *, orchestrator: _RecordingOrchestrator) -> TestClient:
    mocker.patch(
        f"{_PIPELINE_NS}.get_api_config", return_value=ApiConfig(orchestration_mode="direct", allow_request_orchestration_mode_override=False)
    )
    mocker.patch(f"{_PIPELINE_NS}.get_orchestrator_registry", return_value=OrchestratorRegistry({"direct": orchestrator}))
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app, disclosure_mode=DisclosureMode.STRICT)
    return TestClient(app)


@pytest.mark.usefixtures("sandbox_hosted_mode")
class TestBundleStructuresRefusal:
    @pytest.mark.parametrize("path", ["/v1/execute", "/v1/start"])
    def test_bundle_declaring_a_structure_class_is_refused_unimported(self, mocker: MockerFixture, tmp_path: Path, path: str):
        sentinel = tmp_path / "structures-module-ran"
        orchestrator = _RecordingOrchestrator()
        client = _build_client(mocker, orchestrator=orchestrator)

        files = {"main.mthds": VALID_MTHDS, "structures/invoice.py": _structures_py(sentinel=sentinel)}
        response = client.post(path, json={"files": files, "inputs": {"text": "hello"}})

        assert response.status_code == 403, response.text
        assert response.headers["content-type"].startswith("application/problem+json")
        body = response.json()
        assert body["error_type"] == "MethodStructuresRefusedError"
        # Caller-facing even under STRICT disclosure: it names the file and the class, and gives the route.
        assert "structures/invoice.py" in body["detail"]
        assert "Invoice" in body["detail"]
        assert "MTHDS concepts" in body["detail"]
        assert not sentinel.exists(), "the structure module was imported"
        assert orchestrator.dispatches == []

    def test_pipe_func_only_bundle_still_dispatches(self, mocker: MockerFixture):
        orchestrator = _RecordingOrchestrator()
        client = _build_client(mocker, orchestrator=orchestrator)

        files = {"main.mthds": _PIPE_FUNC_MTHDS, "funcs/pipe_func.py": _PIPE_FUNC_PY}
        response = client.post("/v1/start", json={"files": files, "inputs": {"data": "1,2,3"}})

        assert response.status_code in {200, 202}, response.text
        assert orchestrator.dispatches == ["crunch"]
