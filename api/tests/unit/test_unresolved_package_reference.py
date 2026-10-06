"""What the server answers when a bundle calls a method package that cannot be resolved.

The reference is a property of the caller's content, so the answer is the verdict: `/v1/validate` answers `200` with
`is_valid: false`, and the run routes refuse the run with a `422` before anything is dispatched, both carrying one
`unresolved_package_dependency` item that names the reference as written. Fetch-on-miss is off and the installed
store is an empty temporary directory, so the refusal is deterministic and nothing reaches the network.
"""

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipelex.base_exceptions import DisclosureMode, ValidationErrorCategory
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.plugins.orchestrator_registry import OrchestratorRegistry
from pipelex.runtime_bridge.payloads import PipelexPipeDispatchAck, PipelexPipeRunOutput
from pytest_mock import MockerFixture

from pipelex_api.api_config import ApiConfig
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router
from tests.unit._constants import UNRESOLVED_PACKAGE_MTHDS, UNRESOLVED_PACKAGE_REFERENCE

_PIPELINE_NS = "pipelex_api.routes.pipelex.pipeline"


class _RecordingOrchestrator:
    """An async-capable orchestrator that records every dispatch; a refused bundle must reach neither arm."""

    supports_fire_and_forget = True

    def __init__(self) -> None:
        self.dispatches: list[str] = []

    async def execute(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeRunOutput:  # noqa: ARG002
        self.dispatches.append(pipe_job.pipe.code)
        msg = "A refused bundle must not be dispatched."
        raise AssertionError(msg)

    async def start(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeDispatchAck:  # noqa: ARG002
        self.dispatches.append(pipe_job.pipe.code)
        msg = "A refused bundle must not be dispatched."
        raise AssertionError(msg)


def _build_client(
    mocker: MockerFixture, *, tmp_path: Path, disclosure_mode: DisclosureMode, orchestrator: _RecordingOrchestrator | None = None
) -> TestClient:
    mocker.patch("pipelex.cli.installed_methods.GLOBAL_METHODS_DIR", tmp_path / "global-methods")
    mocker.patch("pipelex.cli.installed_methods.PROJECT_METHODS_DIR", tmp_path / "project-methods")
    mocker.patch("pipelex.methods.fetch_on_miss.is_method_fetch_on_miss_enabled", return_value=False)
    mocker.patch(
        f"{_PIPELINE_NS}.get_api_config", return_value=ApiConfig(orchestration_mode="direct", allow_request_orchestration_mode_override=False)
    )
    if orchestrator is not None:
        mocker.patch(f"{_PIPELINE_NS}.get_orchestrator_registry", return_value=OrchestratorRegistry({"direct": orchestrator}))
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app, disclosure_mode=disclosure_mode)
    return TestClient(app)


def _assert_the_package_item(items: list[dict[str, Any]]) -> None:
    assert len(items) == 1, items
    item = items[0]
    assert item["category"] == ValidationErrorCategory.PIPE_VALIDATION
    assert item["error_type"] == "unresolved_package_dependency"
    assert item["pipe_code"] == "echo"
    assert item["domain_code"] == "smoke"
    assert item["missing_pipe_code"] == UNRESOLVED_PACKAGE_REFERENCE
    assert item["field_path"] == "pipe.echo.steps[0].pipe"
    assert "github.com/invented/probe-lib/probe" in item["message"]


class TestUnresolvedPackageReference:
    @pytest.mark.parametrize("disclosure_mode", [DisclosureMode.VERBOSE, DisclosureMode.STRICT])
    def test_validate_answers_the_invalid_verdict(self, mocker: MockerFixture, tmp_path: Path, disclosure_mode: DisclosureMode):
        client = _build_client(mocker, tmp_path=tmp_path, disclosure_mode=disclosure_mode)

        response = client.post("/v1/validate", json={"mthds_contents": [UNRESOLVED_PACKAGE_MTHDS]})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        _assert_the_package_item(body["validation_errors"])

    @pytest.mark.parametrize("disclosure_mode", [DisclosureMode.VERBOSE, DisclosureMode.STRICT])
    @pytest.mark.parametrize("path", ["/v1/execute", "/v1/start"])
    def test_a_run_is_refused_with_the_verdict(self, mocker: MockerFixture, tmp_path: Path, disclosure_mode: DisclosureMode, path: str):
        orchestrator = _RecordingOrchestrator()
        client = _build_client(mocker, tmp_path=tmp_path, disclosure_mode=disclosure_mode, orchestrator=orchestrator)

        response = client.post(path, json={"pipe_code": "echo", "mthds_contents": [UNRESOLVED_PACKAGE_MTHDS], "inputs": {"text": "hello"}})

        assert response.status_code == 422, response.text
        assert response.headers["content-type"].startswith("application/problem+json")
        body = response.json()
        assert body["error_type"] == "ValidateBundleError"
        assert body["error_domain"] == "input"
        _assert_the_package_item(body["validation_errors"])
        # The caller's own content: STRICT keeps the human summary, which is the item's message.
        assert body["detail"] == body["validation_errors"][0]["message"]
        assert orchestrator.dispatches == []
