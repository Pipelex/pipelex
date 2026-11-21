"""A caller's `pipeline_run_id` is held to the runtime's one rule at the wire, on both run routes.

The rule is pipelex's `validate_pipeline_run_id`, which `PipelineApiExtras` runs as a field validator, so a run id
outside it is a 422 naming the field before anything registers, and a well-formed one reaches the run's metadata.
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
_RUN_ID = "run_7Qd2kV"


class _RecordingOrchestrator:
    """Records the `RunMetadata` of every job it is handed, on either arm."""

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
        return PipelexPipeDispatchAck(pipeline_run_id=pipe_job.job_metadata.run_metadata.pipeline_run_id, workflow_id="wf-run-id")


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


@pytest.mark.parametrize("route", _ROUTES)
class TestPipelineRunIdWire:
    def test_a_well_formed_run_id_names_the_run(self, mocker: MockerFixture, route: str) -> None:
        client, orchestrator = _build_client(mocker)

        response = client.post(route, json=_run_body(pipeline_run_id=_RUN_ID))

        assert response.status_code == _SUCCESS_STATUS[route], response.text
        assert response.json()["pipeline_run_id"] == _RUN_ID
        assert [run_metadata.pipeline_run_id for run_metadata in orchestrator.run_metadatas] == [_RUN_ID]

    @pytest.mark.parametrize("bad_run_id", ["", "run/7", "order 42", "run.7", "x" * 129, "untitled", "dry_run_untitled"])
    def test_a_run_id_outside_the_rule_is_a_422_before_the_run(self, mocker: MockerFixture, route: str, bad_run_id: str) -> None:
        client, orchestrator = _build_client(mocker)

        response = client.post(route, json=_run_body(pipeline_run_id=bad_run_id))

        assert_problem(response, status=422, code="request.invalid", field="pipeline_run_id")
        assert orchestrator.run_metadatas == []
