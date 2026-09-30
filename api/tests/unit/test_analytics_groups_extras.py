"""`analytics_groups` must survive the wire -> extras -> runner -> `RunMetadata` hop on both run routes.

Every failure on this path is SILENT by construction. The route hands the validated extras to
`ApiRunner` field by field, so a keyword left out there is dropped with no error; `ApiRunner.start`
builds its job by calling `pipeline_run_setup` itself, so a keyword left out there is dropped too. Either way the run still
answers 200 or 202, and the only symptom is that every span of it arrives in PostHog with no
organization. So these tests run the real `pipeline_run_setup` and read the groups off the
`RunMetadata` the runtime built, rather than off a mocked constructor call.

A stub orchestrator stands in for the backend, registered under an async-capable mode so that
`/execute` (the blocking arm) and `/start` (the fire-and-forget arm) both dispatch to it.
"""

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

from api.api_config import ApiConfig
from api.exception_handlers import register_exception_handlers
from api.routes import router as api_router
from tests.unit._constants import VALID_MTHDS

if TYPE_CHECKING:
    from pipelex.system.job_metadata import RunMetadata

_PIPELINE_NS = "api.routes.pipelex.pipeline"
_MODE = "temporal"
_ROUTES = ["/v1/execute", "/v1/start"]
_SUCCESS_STATUS = {"/v1/execute": 200, "/v1/start": 202}


class _RecordingOrchestrator:
    """Records the `RunMetadata` of every job it is handed, on either arm.

    `execute` echoes the job's input back as the completed output, through the real
    `serialize_completed_output`, so the route's rehydration runs as it does in production. Both arms
    take `delivery_assignment` because the orchestrator protocol does; what the route delivers is
    not what these tests are about.
    """

    supports_fire_and_forget = True

    def __init__(self) -> None:
        self.run_metadatas: list[RunMetadata] = []

    async def execute(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeRunOutput:  # noqa: ARG002
        self.run_metadatas.append(pipe_job.job_metadata.run_metadata)
        working_memory = pipe_job.get_working_memory()
        working_memory.set_alias(alias=MAIN_STUFF_NAME, target=next(iter(working_memory.root)))
        return serialize_completed_output(
            pipe_output=PipeOutput(
                working_memory=working_memory,
                pipeline_run_id=pipe_job.job_metadata.run_metadata.pipeline_run_id,
            ),
            workflow_id=None,
        )

    async def start(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeDispatchAck:  # noqa: ARG002
        self.run_metadatas.append(pipe_job.job_metadata.run_metadata)
        return PipelexPipeDispatchAck(
            pipeline_run_id=pipe_job.job_metadata.run_metadata.pipeline_run_id,
            workflow_id="wf-analytics-groups",
        )


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


class TestAnalyticsGroupsReachTheRun:
    @pytest.mark.parametrize("route", _ROUTES)
    def test_groups_reach_the_run_metadata(self, mocker: MockerFixture, route: str) -> None:
        client, orchestrator = _build_client(mocker)
        groups = {"organization": "org_acme", "workspace": "ws-42"}

        response = client.post(route, json=_run_body(analytics_groups=groups))

        assert response.status_code == _SUCCESS_STATUS[route], response.text
        assert len(orchestrator.run_metadatas) == 1
        assert orchestrator.run_metadatas[0].extras == groups

    @pytest.mark.parametrize("route", _ROUTES)
    @pytest.mark.parametrize(
        "extras",
        [
            pytest.param({}, id="absent"),
            pytest.param({"analytics_groups": None}, id="null"),
            pytest.param({"analytics_groups": {}}, id="empty"),
        ],
    )
    def test_no_groups_means_an_empty_mapping(self, mocker: MockerFixture, route: str, extras: dict[str, Any]) -> None:
        # A run with no groups belongs to no group; it is not refused and nothing is invented.
        client, orchestrator = _build_client(mocker)

        response = client.post(route, json=_run_body(**extras))

        assert response.status_code == _SUCCESS_STATUS[route], response.text
        assert len(orchestrator.run_metadatas) == 1
        assert orchestrator.run_metadatas[0].extras == {}

    @pytest.mark.parametrize("route", _ROUTES)
    @pytest.mark.parametrize(
        "bad_groups",
        [
            pytest.param({"Organization": "org_acme"}, id="type-not-snake-case"),
            pytest.param({"organization": "org acme"}, id="key-with-space"),
            pytest.param({"organization": "org_acme\n"}, id="key-with-trailing-newline"),
            pytest.param({"organization": ""}, id="empty-key"),
            pytest.param({"organization": "a" * 129}, id="overlong-key"),
            pytest.param({f"group_{idx}": "org_acme" for idx in range(6)}, id="over-the-entry-cap"),
            pytest.param({"organization": 42}, id="non-string-key"),
            pytest.param(["organization"], id="not-a-mapping-list"),
            pytest.param("organization", id="not-a-mapping-string"),
        ],
    )
    def test_malformed_groups_are_a_422_naming_the_field(self, mocker: MockerFixture, route: str, bad_groups: Any) -> None:
        # Refused at the wire, before any method is loaded or any job dispatched: the value is
        # quoted into log lines and forwarded to a telemetry backend as a group key.
        client, orchestrator = _build_client(mocker)

        response = client.post(route, json=_run_body(analytics_groups=bad_groups))

        assert response.status_code == 422, response.text
        assert response.headers["content-type"] == "application/problem+json"
        body = response.json()
        assert body["error_type"] == "InvalidAnalyticsGroups"
        assert "analytics_groups" in body["detail"]
        assert orchestrator.run_metadatas == []

    def test_a_body_failing_on_two_extras_gets_the_generic_error_type(self, mocker: MockerFixture) -> None:
        # Naming one of the two fields would send the caller to fix that one and leave the other
        # for the next request, so the classification falls back to the generic type and the
        # detail names both.
        client, orchestrator = _build_client(mocker)

        response = client.post("/v1/start", json=_run_body(storage_scope="../escape", analytics_groups={"Organization": "org_acme"}))

        assert response.status_code == 422, response.text
        body = response.json()
        assert body["error_type"] == "ValidationError"
        assert "storage_scope" in body["detail"]
        assert "analytics_groups" in body["detail"]
        assert orchestrator.run_metadatas == []
