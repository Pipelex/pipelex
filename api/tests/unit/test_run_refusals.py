"""What the run routes answer when the caller's own method refuses the run.

Two moments, both the caller's to fix, so both are a 422 that STRICT disclosure keeps readable:

- **An invalid bundle is refused before any pipe runs, with the validation verdict.** A run loads
  its bundle before it dispatches anything, and the runtime turns every refusal of that load into a
  `ValidateBundleError` carrying the same located `validation_errors` validating the bundle gives,
  whatever check refused it: a misspelled concept used to escape as a 500, and an unknown model as a
  raw model-choice error with no item. The orchestrator is a recording stub here, so the tests also
  pin that nothing was dispatched.
- **A run that fails reports its root fault, located at the failing pipe.** The problem document's
  `error_type`, `title` and `type` are the innermost Pipelex error's, never the run-level wrapper's,
  and its `detail` names the failing pipe and its path from the entry pipe. This one runs the real
  in-process orchestrator on a bundle whose pipes call no model, so it fails the same way whether
  the run is live or dry.
"""

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

from api.api_config import ApiConfig
from api.exception_handlers import register_exception_handlers
from api.routes import router as api_router
from tests.unit._constants import MISMATCHED_PARALLEL_MTHDS, MISSPELLED_CONCEPT_MTHDS, UNKNOWN_MODEL_MTHDS

_PIPELINE_NS = "api.routes.pipelex.pipeline"


class _RecordingOrchestrator:
    """An async-capable orchestrator that records every dispatch; an invalid bundle must reach neither arm."""

    supports_fire_and_forget = True

    def __init__(self) -> None:
        self.dispatches: list[tuple[str, DeliveryAssignment | None]] = []

    async def execute(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeRunOutput:
        self.dispatches.append((pipe_job.pipe.code, delivery_assignment))
        msg = "An invalid bundle must be refused before the run is dispatched."
        raise AssertionError(msg)

    async def start(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeDispatchAck:
        self.dispatches.append((pipe_job.pipe.code, delivery_assignment))
        msg = "An invalid bundle must be refused before the run is dispatched."
        raise AssertionError(msg)


def _build_client(mocker: MockerFixture, *, disclosure_mode: DisclosureMode, orchestrator: _RecordingOrchestrator | None = None) -> TestClient:
    """An app on the `direct` mode; `orchestrator` replaces the registered one when given."""
    mocker.patch(
        f"{_PIPELINE_NS}.get_api_config", return_value=ApiConfig(orchestration_mode="direct", allow_request_orchestration_mode_override=False)
    )
    if orchestrator is not None:
        mocker.patch(f"{_PIPELINE_NS}.get_orchestrator_registry", return_value=OrchestratorRegistry({"direct": orchestrator}))
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app, disclosure_mode=disclosure_mode)
    return TestClient(app)


class TestRunRefusals:
    @pytest.mark.parametrize("disclosure_mode", [DisclosureMode.VERBOSE, DisclosureMode.STRICT])
    @pytest.mark.parametrize("path", ["/v1/execute", "/v1/start"])
    @pytest.mark.parametrize(
        ("mthds_content", "expected_item"),
        [
            (
                MISSPELLED_CONCEPT_MTHDS,
                {
                    "error_type": "unresolved_concept",
                    "concept_code": "Summry",
                    "field_path": "pipe.echo.output",
                    "field_name": "output",
                },
            ),
            (
                UNKNOWN_MODEL_MTHDS,
                {
                    "error_type": "unknown_model",
                    "model_reference": "no-such-model-in-any-deck",
                    "model_type": "llm",
                    "field_path": "pipe.echo.model",
                    "field_name": "model",
                },
            ),
        ],
        ids=["misspelled_concept", "unknown_model"],
    )
    def test_invalid_bundle_is_a_422_with_located_items(
        self,
        mocker: MockerFixture,
        disclosure_mode: DisclosureMode,
        path: str,
        mthds_content: str,
        expected_item: dict[str, Any],
    ):
        orchestrator = _RecordingOrchestrator()
        client = _build_client(mocker, disclosure_mode=disclosure_mode, orchestrator=orchestrator)

        response = client.post(path, json={"pipe_code": "echo", "mthds_contents": [mthds_content], "inputs": {"text": "hello"}})

        assert response.status_code == 422, response.text
        assert response.headers["content-type"].startswith("application/problem+json")
        body = response.json()
        assert body["error_type"] == "ValidateBundleError"
        assert body["error_domain"] == "input"
        assert body["user_action"]["kind"] == "change_input"
        items: list[dict[str, Any]] = body["validation_errors"]
        assert len(items) == 1, items
        item = items[0]
        assert item["category"] == ValidationErrorCategory.PIPE_VALIDATION
        assert item["pipe_code"] == "echo"
        assert item["domain_code"] == "smoke"
        for field_name, expected_value in expected_item.items():
            assert item[field_name] == expected_value, item
        # The verdict is the caller's own bundle: STRICT keeps the human summary, which is the item's message.
        assert body["detail"] == item["message"]
        # Refused while the bundle loads: nothing reached the orchestrator.
        assert orchestrator.dispatches == []

    @pytest.mark.parametrize("disclosure_mode", [DisclosureMode.VERBOSE, DisclosureMode.STRICT])
    def test_run_failure_reports_its_root_fault_at_the_failing_pipe(self, mocker: MockerFixture, disclosure_mode: DisclosureMode):
        client = _build_client(mocker, disclosure_mode=disclosure_mode)

        response = client.post("/v1/execute", json={"mthds_contents": [MISMATCHED_PARALLEL_MTHDS], "inputs": {"topic": "tides"}})

        assert response.status_code == 422, response.text
        assert response.headers["content-type"].startswith("application/problem+json")
        body = response.json()
        # The root fault's class, not the run-level `PipelineExecutionError` that wraps it.
        assert body["error_type"] == "StuffFactoryError"
        assert body["type"] == "https://docs.pipelex.com/latest/errors/stuff-factory-error/"
        assert body["error_domain"] == "input"
        # Located at the failing step, with its path from the entry pipe, and kept under STRICT
        # because the fault is the caller's own method.
        assert body["detail"].startswith("Pipe 'analyze_topic' failed (review_topic → analyze_topic): "), body["detail"]
        # The next step says which of the two multiplicities to change.
        assert body["user_action"]["kind"] == "change_input"
        assert "Branch 'draft_idea' gives result 'ideas' as a single 'Idea'" in body["user_action"]["detail"]
        assert "validation_errors" not in body
