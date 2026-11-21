from typing import TYPE_CHECKING, Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.plugins.orchestrator_registry import OrchestratorRegistry
from pipelex.runtime_bridge.payloads import PipelexPipeDispatchAck, PipelexPipeRunOutput
from pipelex.runtime_bridge.serialization import serialize_completed_output
from pytest_mock import MockerFixture

from pipelex_api.api_config import ApiConfig
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router
from tests.unit._constants import VALID_MTHDS
from tests.unit._problems import assert_problem

if TYPE_CHECKING:
    from pipelex.system.job_metadata import RunMetadata

_PIPELINE_NS = "pipelex_api.routes.pipelex.pipeline"
_MODE = "temporal"
_ROUTES = ["/v1/execute", "/v1/start"]
_SUCCESS_STATUS = {"/v1/execute": 200, "/v1/start": 202}


class _RecordingOrchestrator:
    """Records the `RunMetadata` of every job it is handed, on either arm, as the analytics-groups test's does."""

    supports_fire_and_forget = True

    def __init__(self) -> None:
        self.run_metadatas: list[RunMetadata] = []

    async def execute(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeRunOutput:  # noqa: ARG002
        self.run_metadatas.append(pipe_job.job_metadata.run_metadata)
        working_memory = pipe_job.get_working_memory()
        working_memory.set_alias(alias=MAIN_STUFF_NAME, target=next(iter(working_memory.root)))
        return serialize_completed_output(
            pipe_output=PipeOutput(working_memory=working_memory, pipeline_run_id=pipe_job.job_metadata.run_metadata.pipeline_run_id),
            workflow_id=None,
        )

    async def start(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeDispatchAck:  # noqa: ARG002
        self.run_metadatas.append(pipe_job.job_metadata.run_metadata)
        return PipelexPipeDispatchAck(pipeline_run_id=pipe_job.job_metadata.run_metadata.pipeline_run_id, workflow_id="wf-run-method")


def _build_client(mocker: MockerFixture) -> tuple[TestClient, _RecordingOrchestrator]:
    config = ApiConfig(orchestration_mode=_MODE, allow_request_orchestration_mode_override=False)
    mocker.patch(f"{_PIPELINE_NS}.get_api_config", return_value=config)
    orchestrator = _RecordingOrchestrator()
    mocker.patch(f"{_PIPELINE_NS}.get_orchestrator_registry", return_value=OrchestratorRegistry({_MODE: orchestrator}))
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app), orchestrator


def _run_body(**extras: Any) -> dict[str, Any]:
    return {"pipe_code": "echo", "mthds_contents": [VALID_MTHDS], "inputs": {"text": "hello"}, **extras}


class TestRunMethodExtrasReachTheRun:
    @pytest.mark.parametrize("route", _ROUTES)
    @pytest.mark.parametrize("capture_pipe_codes", [True, False])
    def test_the_method_key_and_the_pipe_code_setting_reach_the_run_metadata(
        self, mocker: MockerFixture, route: str, capture_pipe_codes: bool
    ) -> None:
        client, orchestrator = _build_client(mocker)

        response = client.post(route, json=_run_body(method_key="mt_abc123", capture_pipe_codes=capture_pipe_codes))

        assert response.status_code == _SUCCESS_STATUS[route], response.text
        (run_metadata,) = orchestrator.run_metadatas
        # The wire's neutral key is the run's method id inside the runtime.
        assert run_metadata.method_id == "mt_abc123"
        assert run_metadata.capture_pipe_codes is capture_pipe_codes
        # An inline source names no published package.
        assert run_metadata.method_address is None

    @pytest.mark.parametrize("route", _ROUTES)
    def test_a_run_naming_neither_leaves_both_unset(self, mocker: MockerFixture, route: str) -> None:
        client, orchestrator = _build_client(mocker)

        response = client.post(route, json=_run_body())

        assert response.status_code == _SUCCESS_STATUS[route], response.text
        (run_metadata,) = orchestrator.run_metadatas
        assert run_metadata.method_id is None
        assert run_metadata.capture_pipe_codes is None

    @pytest.mark.parametrize("route", _ROUTES)
    @pytest.mark.parametrize(
        "bad_method_key",
        [
            pytest.param("", id="empty"),
            pytest.param("mt_abc@3", id="version-selector"),
            pytest.param("mt_abc\nforged=1", id="newline"),
            pytest.param("m" * 129, id="overlong"),
            pytest.param(42, id="not-a-string"),
        ],
    )
    def test_a_malformed_method_key_is_a_422_naming_the_field(self, mocker: MockerFixture, route: str, bad_method_key: Any) -> None:
        client, orchestrator = _build_client(mocker)

        response = client.post(route, json=_run_body(method_key=bad_method_key))

        body = assert_problem(response, status=422, code="request.invalid")
        assert body["params"]["field"] == "method_key", body
        assert orchestrator.run_metadatas == []

    @pytest.mark.parametrize("route", _ROUTES)
    def test_a_non_boolean_pipe_code_setting_is_a_422_naming_the_field(self, mocker: MockerFixture, route: str) -> None:
        client, orchestrator = _build_client(mocker)

        response = client.post(route, json=_run_body(capture_pipe_codes="sometimes"))

        body = assert_problem(response, status=422, code="request.invalid")
        assert body["params"]["field"] == "capture_pipe_codes", body
        assert orchestrator.run_metadatas == []
