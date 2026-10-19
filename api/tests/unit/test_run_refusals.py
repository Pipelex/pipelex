"""What the run routes answer when the caller's own method refuses the run.

Two moments, both the method's to fix, so both are a 422 whose caller view says everything needed to fix it:

- **An invalid bundle is refused before any pipe runs, with the validation verdict.** A run loads
  its bundle before it dispatches anything, and the runtime turns every refusal of that load into a
  `method.invalid` problem whose `errors` are the same located faults validating the bundle gives,
  whatever check refused it: a misspelled concept used to escape as a 500, and an unknown model as a
  raw model-choice error with no item. The orchestrator is a recording stub here, so the tests also
  pin that nothing was dispatched.
- **A run that fails reports its root fault, located at the failing pipe.** The problem's `code`,
  `title` and `type` are the innermost fault's, never the run-level wrapper's, and its `location`
  names the failing pipe and its path from the entry pipe. This one runs the real in-process
  orchestrator on a bundle whose pipes call no model, so it fails the same way whether the run is
  live or dry.
"""

from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from mthds.protocol.problem.registry import CoreCode
from pipelex.errors.problem import ProblemView
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.plugins.orchestrator_registry import OrchestratorRegistry
from pipelex.runtime_bridge.payloads import PipelexPipeDispatchAck, PipelexPipeRunOutput
from pytest_mock import MockerFixture

from pipelex_api.api_config import ApiConfig
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.problem_view import mark_operator_request
from pipelex_api.routes import router as api_router
from tests.unit._constants import MISMATCHED_PARALLEL_MTHDS, MISSPELLED_CONCEPT_MTHDS, UNKNOWN_MODEL_MTHDS

_PIPELINE_NS = "pipelex_api.routes.pipelex.pipeline"


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


def _build_client(mocker: MockerFixture, *, view: ProblemView, orchestrator: _RecordingOrchestrator | None = None) -> TestClient:
    """An app on the `direct` mode answering in `view`; `orchestrator` replaces the registered one when given."""
    mocker.patch(
        f"{_PIPELINE_NS}.get_api_config", return_value=ApiConfig(orchestration_mode="direct", allow_request_orchestration_mode_override=False)
    )
    if orchestrator is not None:
        mocker.patch(f"{_PIPELINE_NS}.get_orchestrator_registry", return_value=OrchestratorRegistry({"direct": orchestrator}))
    app = FastAPI()
    match view:
        case ProblemView.OPERATOR:
            app.include_router(api_router, prefix="/v1", dependencies=[Depends(mark_operator_request)])
        case ProblemView.CALLER:
            app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


class TestRunRefusals:
    @pytest.mark.parametrize("view", [ProblemView.OPERATOR, ProblemView.CALLER])
    @pytest.mark.parametrize("path", ["/v1/execute", "/v1/start"])
    @pytest.mark.parametrize(
        ("mthds_content", "expected_item"),
        [
            (
                MISSPELLED_CONCEPT_MTHDS,
                {
                    "code": CoreCode.METHOD_CONCEPT_UNRESOLVED,
                    "detail": "The method names the concept 'Summry', which no library declares.",
                    "params": {"concept": "Summry", "suggestions": []},
                    "location": {"pipe": "echo", "field": "output"},
                },
            ),
            (
                UNKNOWN_MODEL_MTHDS,
                {
                    "code": CoreCode.MODEL_UNKNOWN,
                    "detail": "The method names the llm model 'no-such-model-in-any-deck', which no catalog knows.",
                    "params": {"model": "no-such-model-in-any-deck", "model_type": "llm", "suggestions": []},
                    "location": {"pipe": "echo", "field": "model"},
                },
            ),
        ],
        ids=["misspelled_concept", "unknown_model"],
    )
    def test_invalid_bundle_is_a_422_with_located_items(
        self,
        mocker: MockerFixture,
        view: ProblemView,
        path: str,
        mthds_content: str,
        expected_item: dict[str, Any],
    ):
        orchestrator = _RecordingOrchestrator()
        client = _build_client(mocker, view=view, orchestrator=orchestrator)

        response = client.post(path, json={"pipe_code": "echo", "mthds_contents": [mthds_content], "inputs": {"text": "hello"}})

        assert response.status_code == 422, response.text
        assert response.headers["content-type"].startswith("application/problem+json")
        body = response.json()
        assert body["code"] == CoreCode.METHOD_INVALID
        assert body["domain"] == "method"
        assert body["next_step"]["kind"] == "change_method"
        # Each fault is an item with its own code, its own sentence and its place in the method, in either view.
        assert body["errors"] == [expected_item]
        match view:
            case ProblemView.OPERATOR:
                assert body["diagnostics"]["error_class"] == "ValidateBundleError"
            case ProblemView.CALLER:
                assert "diagnostics" not in body
        # Refused while the bundle loads: nothing reached the orchestrator.
        assert orchestrator.dispatches == []

    @pytest.mark.parametrize("view", [ProblemView.OPERATOR, ProblemView.CALLER])
    def test_run_failure_reports_its_root_fault_at_the_failing_pipe(self, mocker: MockerFixture, view: ProblemView):
        client = _build_client(mocker, view=view)

        response = client.post("/v1/execute", json={"mthds_contents": [MISMATCHED_PARALLEL_MTHDS], "inputs": {"topic": "tides"}})

        assert response.status_code == 422, response.text
        assert response.headers["content-type"].startswith("application/problem+json")
        body = response.json()
        # The code names the root fault, a branch's multiplicity that is not its field's, never the run-level wrapper.
        assert body["code"] == CoreCode.PIPE_OUTPUT_MULTIPLICITY
        assert body["type"] == "https://mthds.ai/errors/pipe.output_multiplicity"
        assert body["domain"] == "method"
        assert body["detail"] == "Pipe 'analyze_topic' produced an output of the multiplicity 'single', but its output 'ideas' is declared 'list'."
        assert body["params"] == {"output": "ideas", "declared": "list", "produced": "single", "pipe": "analyze_topic"}
        # Located at the failing step, with its path from the entry pipe.
        assert body["location"] == {"pipe": "analyze_topic", "path": ["review_topic", "analyze_topic"]}
        # The next step says which of the two multiplicities to change.
        assert body["next_step"] == {
            "kind": "change_method",
            "detail": "Declare the output 'ideas' as 'single', or make pipe 'analyze_topic' produce 'list'.",
        }
        assert "errors" not in body
        match view:
            case ProblemView.OPERATOR:
                # The root fault's class, not the run-level `PipelineExecutionError` that wraps it.
                assert body["diagnostics"]["error_class"] == "StuffFactoryError"
                assert "Branch 'draft_idea' gives result 'ideas' as a single 'Idea'" in body["diagnostics"]["message"]
            case ProblemView.CALLER:
                assert "diagnostics" not in body
