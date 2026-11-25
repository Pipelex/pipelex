from typing import TYPE_CHECKING, Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipelex.config import get_config
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
from tests.unit._constants import FIVE_IDEAS_MTHDS, VALID_MTHDS
from tests.unit._problems import assert_problem

if TYPE_CHECKING:
    from pipelex.system.job_metadata import RunMetadata

_PIPELINE_NS = "pipelex_api.routes.pipelex.pipeline"
_MODE = "temporal"
_RUN_ROUTES = ["/v1/execute", "/v1/start"]
_SUCCESS_STATUS = {"/v1/execute": 200, "/v1/start": 202}
_OVER_LIMIT = "pipelex.deployment.declared_count_over_limit"
_SLOT = "the output of the pipe 'five_ideas'"


class _RecordingOrchestrator:
    """Records the `RunMetadata` of every job it is handed, and runs nothing."""

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
        return PipelexPipeDispatchAck(pipeline_run_id=pipe_job.job_metadata.run_metadata.pipeline_run_id, workflow_id="wf-declared-count")


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


def _build_run_client(mocker: MockerFixture) -> tuple[TestClient, _RecordingOrchestrator]:
    config = ApiConfig(orchestration_mode=_MODE, allow_request_orchestration_mode_override=False)
    mocker.patch(f"{_PIPELINE_NS}.get_api_config", return_value=config)
    orchestrator = _RecordingOrchestrator()
    mocker.patch(f"{_PIPELINE_NS}.get_orchestrator_registry", return_value=OrchestratorRegistry({_MODE: orchestrator}))
    return _build_client(), orchestrator


def _lower_the_deployments_maximum(mocker: MockerFixture) -> None:
    """A deployment allowing four items for one slot, whose ceiling lets a request raise that to five."""
    mocker.patch.object(get_config().interpreter.method_limits, "max_declared_item_count", 4)
    mocker.patch.object(get_config().interpreter.method_limits, "max_declared_item_count_ceiling", 5)


def _over_limit_params(*, errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [error["params"] for error in errors if error["code"] == _OVER_LIMIT]


class TestMaxDeclaredItemCount:
    @pytest.mark.parametrize("route", _RUN_ROUTES)
    def test_a_runs_maximum_reaches_the_run_metadata(self, mocker: MockerFixture, route: str) -> None:
        client, orchestrator = _build_run_client(mocker)

        response = client.post(
            route, json={"pipe_code": "echo", "mthds_contents": [VALID_MTHDS], "inputs": {"text": "hi"}, "max_declared_item_count": 500}
        )

        assert response.status_code == _SUCCESS_STATUS[route], response.text
        (run_metadata,) = orchestrator.run_metadatas
        assert run_metadata.max_declared_item_count == 500

    @pytest.mark.parametrize("route", [*_RUN_ROUTES, "/v1/validate", "/v1/resolve"])
    def test_a_maximum_past_the_deployments_ceiling_is_a_422_naming_the_field(self, mocker: MockerFixture, route: str) -> None:
        """The field is public JSON: a caller cannot raise its own maximum past the ceiling, 1,000 by default."""
        client, orchestrator = _build_run_client(mocker)
        body: dict[str, Any] = {"files": {"main.mthds": VALID_MTHDS}} if route == "/v1/resolve" else {"mthds_contents": [VALID_MTHDS]}

        response = client.post(route, json={**body, "inputs": {"text": "hi"}, "max_declared_item_count": 1001})

        assert_problem(response, status=422, code="request.invalid", field="max_declared_item_count")
        assert orchestrator.run_metadatas == []

    @pytest.mark.parametrize("route", _RUN_ROUTES)
    def test_a_deployment_raising_its_ceiling_lets_a_trusted_front_raise_a_runs_maximum(self, mocker: MockerFixture, route: str) -> None:
        mocker.patch.object(get_config().interpreter.method_limits, "max_declared_item_count_ceiling", 5000)
        client, orchestrator = _build_run_client(mocker)

        response = client.post(
            route, json={"pipe_code": "echo", "mthds_contents": [VALID_MTHDS], "inputs": {"text": "hi"}, "max_declared_item_count": 5000}
        )

        assert response.status_code == _SUCCESS_STATUS[route], response.text
        (run_metadata,) = orchestrator.run_metadatas
        assert run_metadata.max_declared_item_count == 5000

    @pytest.mark.parametrize("route", _RUN_ROUTES)
    def test_an_output_multiplicity_past_the_maximum_is_refused_before_the_run_starts(self, mocker: MockerFixture, route: str) -> None:
        """A run's own `output_multiplicity` is held to the maximum in force, the deployment's here, which a lower request maximum leaves alone."""
        _lower_the_deployments_maximum(mocker)
        client, orchestrator = _build_run_client(mocker)
        body = {"pipe_code": "echo", "mthds_contents": [VALID_MTHDS], "inputs": {"text": "hi"}, "max_declared_item_count": 2}

        accepted = client.post(route, json={**body, "output_multiplicity": 4})
        refused = client.post(route, json={**body, "output_multiplicity": 5})

        assert accepted.status_code == _SUCCESS_STATUS[route], accepted.text
        assert refused.status_code == 422, refused.text
        assert refused.json()["code"] == _OVER_LIMIT
        assert refused.json()["params"] == {"slot": "the run's output, with `output_multiplicity`", "count": 5, "limit": 4}
        assert len(orchestrator.run_metadatas) == 1

    @pytest.mark.parametrize("route", _RUN_ROUTES)
    def test_a_run_declaring_more_than_its_maximum_is_refused_before_it_starts(self, mocker: MockerFixture, route: str) -> None:
        _lower_the_deployments_maximum(mocker)
        client, orchestrator = _build_run_client(mocker)

        response = client.post(route, json={"mthds_contents": [FIVE_IDEAS_MTHDS], "inputs": {"text": "hi"}, "max_declared_item_count": 2})

        assert response.status_code == 422, response.text
        assert _over_limit_params(errors=response.json()["errors"]) == [{"slot": _SLOT, "count": 5, "limit": 4}]
        assert orchestrator.run_metadatas == []

    @pytest.mark.parametrize("route", [*_RUN_ROUTES, "/v1/validate", "/v1/resolve"])
    @pytest.mark.parametrize("bad_maximum", [0, -1, 1_000_000_000, "many", True, False, "5", 5.0])
    def test_a_maximum_no_runtime_may_set_is_a_422_naming_the_field(self, mocker: MockerFixture, route: str, bad_maximum: Any) -> None:
        client, _orchestrator = _build_run_client(mocker)
        body: dict[str, Any] = {"files": {"main.mthds": VALID_MTHDS}} if route == "/v1/resolve" else {"mthds_contents": [VALID_MTHDS]}

        response = client.post(route, json={**body, "max_declared_item_count": bad_maximum})

        assert_problem(response, status=422, code="request.invalid", field="max_declared_item_count")

    @pytest.mark.parametrize(
        ("maximum", "is_valid"),
        [
            pytest.param(None, False, id="deployment-maximum"),
            pytest.param(2, False, id="a-lower-maximum-lowers-nothing"),
            pytest.param(5, True, id="a-higher-maximum-raises-it"),
        ],
    )
    def test_a_validation_loads_the_method_under_the_requests_maximum(self, mocker: MockerFixture, maximum: int | None, is_valid: bool) -> None:
        _lower_the_deployments_maximum(mocker)
        response = _build_client().post("/v1/validate", json={"mthds_contents": [FIVE_IDEAS_MTHDS], "max_declared_item_count": maximum})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is is_valid, body
        if not is_valid:
            assert _over_limit_params(errors=body["errors"]) == [{"slot": _SLOT, "count": 5, "limit": 4}]

    @pytest.mark.parametrize(
        ("route", "route_fields"),
        [
            pytest.param("/v1/resolve", {}, id="resolve"),
            pytest.param("/v1/codegen", {"kind": "types", "target": "python-pydantic"}, id="codegen"),
            pytest.param("/v1/pipe-io", {}, id="pipe-io"),
        ],
    )
    def test_a_method_route_loads_the_method_under_the_requests_maximum(
        self, mocker: MockerFixture, route: str, route_fields: dict[str, str]
    ) -> None:
        _lower_the_deployments_maximum(mocker)
        client = _build_client()
        body = {"files": {"main.mthds": FIVE_IDEAS_MTHDS}, **route_fields}

        accepted = client.post(route, json={**body, "max_declared_item_count": 5})
        refused = client.post(route, json={**body, "max_declared_item_count": 2})

        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["is_valid"] is True, accepted.text
        assert refused.status_code == 200, refused.text
        assert refused.json()["is_valid"] is False
        assert _over_limit_params(errors=refused.json()["errors"]) == [{"slot": _SLOT, "count": 5, "limit": 4}]
