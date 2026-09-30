"""`read_scope` must survive the wire -> extras -> runner -> `RunMetadata` hop on both run routes.

Like the storage scope, a read scope dropped on the way is silent: the run still answers 200 or 202,
and the only symptom is a run that reads every tenant's keys. So these tests run the real
`pipeline_run_setup` and read the scope off the `RunMetadata` the runtime built. They also pin the
fallback (the caller's own id when the deployment identifies callers, unscoped when it is
single-tenant) and the 422 that replaces the runtime's bare `ValueError` when the storage scope does
not lie under the read scope.
"""

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.plugins.orchestrator_registry import OrchestratorRegistry
from pipelex.runtime_bridge.payloads import PipelexPipeDispatchAck, PipelexPipeRunOutput
from pipelex.runtime_bridge.serialization import serialize_completed_output
from pipelex.system.storage_scope import LOCAL_STORAGE_SCOPE, SINGLE_TENANT_USER_ID
from pytest_mock import MockerFixture

from api.api_config import ApiConfig
from api.exception_handlers import register_exception_handlers
from api.routes import router as api_router
from api.security import RequestUser
from tests.unit._constants import VALID_MTHDS

if TYPE_CHECKING:
    from pipelex.system.job_metadata import RunMetadata

_PIPELINE_NS = "api.routes.pipelex.pipeline"
_MODE = "temporal"
_ROUTES = ["/v1/execute", "/v1/start"]
_SUCCESS_STATUS = {"/v1/execute": 200, "/v1/start": 202}
_USER_ID = "user_a"


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
        return PipelexPipeDispatchAck(pipeline_run_id=pipe_job.job_metadata.run_metadata.pipeline_run_id, workflow_id="wf-read-scope")


def _build_client(mocker: MockerFixture, *, user_id: str | None = None) -> tuple[TestClient, _RecordingOrchestrator]:
    """An app on a stub async-capable orchestrator; `user_id` makes it a deployment that identifies callers."""
    config = ApiConfig(orchestration_mode=_MODE, allow_request_orchestration_mode_override=False)
    mocker.patch(f"{_PIPELINE_NS}.get_api_config", return_value=config)
    orchestrator = _RecordingOrchestrator()
    mocker.patch(f"{_PIPELINE_NS}.get_orchestrator_registry", return_value=OrchestratorRegistry({_MODE: orchestrator}))
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    if user_id is not None:
        # The shape `api.security` binds on an authenticated request.
        async def _bind_user(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
            request.state.user = RequestUser(user_id=user_id)
            return await call_next(request)

        app.middleware("http")(_bind_user)

    return TestClient(app), orchestrator


def _run_body(**extras: Any) -> dict[str, Any]:
    return {"pipe_code": "echo", "mthds_contents": [VALID_MTHDS], "inputs": {"text": "hello"}, **extras}


@pytest.mark.parametrize("route", _ROUTES)
class TestReadScopeReachesTheRun:
    def test_body_read_scope_reaches_the_run_metadata(self, mocker: MockerFixture, route: str) -> None:
        client, orchestrator = _build_client(mocker)

        response = client.post(route, json=_run_body(storage_scope="org_acme/mt_1/run_7", read_scope="org_acme"))

        assert response.status_code == _SUCCESS_STATUS[route], response.text
        assert len(orchestrator.run_metadatas) == 1
        assert orchestrator.run_metadatas[0].read_scope == "org_acme"
        assert orchestrator.run_metadatas[0].storage_scope == "org_acme/mt_1/run_7"

    def test_single_tenant_default_is_unscoped(self, mocker: MockerFixture, route: str) -> None:
        client, orchestrator = _build_client(mocker)

        response = client.post(route, json=_run_body())

        assert response.status_code == _SUCCESS_STATUS[route], response.text
        assert orchestrator.run_metadatas[0].read_scope is None
        assert orchestrator.run_metadatas[0].storage_scope == SINGLE_TENANT_USER_ID

    def test_identified_caller_default_is_their_own_id(self, mocker: MockerFixture, route: str) -> None:
        client, orchestrator = _build_client(mocker, user_id=_USER_ID)

        response = client.post(route, json=_run_body())

        assert response.status_code == _SUCCESS_STATUS[route], response.text
        assert orchestrator.run_metadatas[0].read_scope == _USER_ID
        assert orchestrator.run_metadatas[0].storage_scope == _USER_ID


@pytest.mark.parametrize("route", _ROUTES)
class TestReadScopeRefusals:
    @pytest.mark.parametrize("bad_scope", ["../etc", "/absolute", "org//empty", "", "a/b/c/d"])
    def test_malformed_read_scope_is_refused_at_the_wire(self, mocker: MockerFixture, route: str, bad_scope: str) -> None:
        client, orchestrator = _build_client(mocker)

        response = client.post(route, json=_run_body(read_scope=bad_scope))

        assert response.status_code == 422, response.text
        assert response.json()["error_type"] == "InvalidReadScope"
        assert orchestrator.run_metadatas == []

    def test_storage_scope_outside_the_read_scope_is_a_422(self, mocker: MockerFixture, route: str) -> None:
        client, orchestrator = _build_client(mocker)

        response = client.post(route, json=_run_body(storage_scope="org_other/mt_1/run_7", read_scope="org_acme"))

        assert response.status_code == 422, response.text
        body = response.json()
        assert body["error_type"] == "InvalidReadScope"
        assert "was sent" in body["detail"]
        assert orchestrator.run_metadatas == []

    def test_host_storage_scope_without_a_read_scope_fails_closed(self, mocker: MockerFixture, route: str) -> None:
        # A multi-tenant host that forgets the read scope gets the caller's id as the default, under
        # which its own storage scope does not lie: refused, rather than reading across tenants.
        client, orchestrator = _build_client(mocker, user_id=_USER_ID)

        response = client.post(route, json=_run_body(storage_scope="org_acme/mt_1/run_7"))

        assert response.status_code == 422, response.text
        body = response.json()
        assert body["error_type"] == "InvalidReadScope"
        assert "defaulted to the caller's id" in body["detail"]
        assert orchestrator.run_metadatas == []

    def test_local_storage_sentinel_beside_a_read_scope_is_a_422(self, mocker: MockerFixture, route: str) -> None:
        client, orchestrator = _build_client(mocker)

        response = client.post(route, json=_run_body(storage_scope=LOCAL_STORAGE_SCOPE, read_scope=LOCAL_STORAGE_SCOPE))

        assert response.status_code == 422, response.text
        assert response.json()["error_type"] == "InvalidReadScope"
        assert orchestrator.run_metadatas == []
