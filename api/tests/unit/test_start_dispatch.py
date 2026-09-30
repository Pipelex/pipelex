"""`/start` is HONEST about fire-and-forget: it acks only when the resolved backend is async-capable.

Fire-and-forget vs blocking is the ENDPOINT's delivery axis, never configured: `/execute` and
`/validate` dispatch with `BLOCKING`, while `/start` dispatches with `FIRE_AND_FORGET`. So `/start`
checks the resolved `orchestration_mode`'s orchestrator BEFORE any library load: an async-capable
orchestrator (`supports_fire_and_forget=True`, e.g. `temporal`) acks `202` with its `workflow_id`,
while a blocking-only orchestrator (`supports_fire_and_forget=False`, e.g. the in-process `direct`
base) is refused HONESTLY with a `400` (`StartRequiresAsyncOrchestration`) instead of silently
running blocking and acking. This pins both arms end-to-end on `POST /start`, with a stub orchestrator
registered under the resolved mode (the boot slot is never used).
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.plugins.orchestrator_registry import OrchestratorRegistry
from pipelex.runtime_bridge.payloads import PipelexPipeDispatchAck, PipelexPipeRunOutput
from pytest_mock import MockerFixture

from api.api_config import ApiConfig
from api.exception_handlers import register_exception_handlers
from api.routes import router as api_router
from tests.unit._constants import VALID_MTHDS

_PIPELINE_NS = "api.routes.pipelex.pipeline"


class _RecordingStub:
    """Stand-in orchestrator that records its dispatch and returns the configured `workflow_id`.

    `supports_fire_and_forget` is the capability `/start` reads BEFORE dispatch: a True stub models
    an async-capable backend (Temporal) that acks immediately with a `workflow_id`; a False stub
    models a blocking-only backend (`direct`) that `/start` must refuse honestly. `start` records its
    dispatch and returns the `PipelexPipeDispatchAck` (ids only) an async backend acks with; `execute`
    (the blocking arm) is present only to satisfy the protocol — `/start` never drives it.
    """

    def __init__(self, *, workflow_id: str, supports_fire_and_forget: bool) -> None:
        self.calls: list[dict[str, object]] = []
        self._workflow_id = workflow_id
        self.supports_fire_and_forget = supports_fire_and_forget

    async def execute(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeRunOutput:
        msg = "/start drives the fire-and-forget `start` arm; `execute` must not be reached."
        raise NotImplementedError(msg)

    async def start(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeDispatchAck:
        self.calls.append({"delivery_assignment": delivery_assignment})
        return PipelexPipeDispatchAck(
            pipeline_run_id=pipe_job.job_metadata.run_metadata.pipeline_run_id,
            workflow_id=self._workflow_id,
        )


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


def _force_config(mocker: MockerFixture, *, mode: str) -> None:
    config = ApiConfig(orchestration_mode=mode, allow_request_orchestration_mode_override=False)
    mocker.patch(f"{_PIPELINE_NS}.get_api_config", return_value=config)


def _register_stub(mocker: MockerFixture, *, mode: str, stub: _RecordingStub) -> None:
    mocker.patch(f"{_PIPELINE_NS}.get_orchestrator_registry", return_value=OrchestratorRegistry({mode: stub}))


class TestStartCapabilityGate:
    """End-to-end: `POST /start` acks only when the resolved backend can honor fire-and-forget."""

    def test_start_acks_when_orchestrator_is_async_capable(self, mocker: MockerFixture) -> None:
        # A `temporal` deployment whose orchestrator is async-capable: /start drives the fire-and-forget
        # `start` arm and acks 202 with the workflow_id the orchestrator returns immediately.
        _force_config(mocker, mode="temporal")
        stub = _RecordingStub(workflow_id="wf-123", supports_fire_and_forget=True)
        _register_stub(mocker, mode="temporal", stub=stub)

        response = _build_client().post(
            "/v1/start",
            json={"pipe_code": "echo", "mthds_contents": [VALID_MTHDS], "inputs": {"text": "hello"}},
        )

        assert response.status_code == 202, response.text
        body = response.json()
        assert body["state"] == "STARTED"
        assert body["workflow_id"] == "wf-123"
        # /start drives the fire-and-forget `start` arm exactly once — the caller never chooses delivery.
        assert len(stub.calls) == 1

    def test_start_honestly_400s_when_orchestrator_is_blocking_only(self, mocker: MockerFixture) -> None:
        # The orchestrator-agnostic base (`direct`) is blocking-only: /start refuses honestly with a
        # 400 BEFORE any dispatch (the capability check runs before pipeline_run_setup), so the stub's
        # `execute` is never awaited — no silent block-and-ack.
        _force_config(mocker, mode="direct")
        # workflow_id is a placeholder: the blocking-only backend is refused before `start` is ever
        # reached, so this value is never observed.
        stub = _RecordingStub(workflow_id="wf-unused", supports_fire_and_forget=False)
        _register_stub(mocker, mode="direct", stub=stub)

        response = _build_client().post(
            "/v1/start",
            json={"pipe_code": "echo", "mthds_contents": [VALID_MTHDS], "inputs": {"text": "hello"}},
        )

        assert response.status_code == 400, response.text
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.json()["error_type"] == "StartRequiresAsyncOrchestration"
        assert stub.calls == []
