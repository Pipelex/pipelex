"""Cross-path consistency of the API's failure surfaces.

A failure reaches its readers along three paths:

1. The **synchronous HTTP path**: `POST /execute`, and every other route that lets a `PipelexError`
   propagate, answers the error's problem through `problem_response`, in the view of whoever made
   the request (`pipelex_api.problem_view`).
2. The **caller's webhooks**: each of a run's `callback_urls` receives the signed `run.finished`
   event, whose `data.error` is the run's problem in the caller's view, whoever started the run, as
   the caller-webhook contract specifies.
3. The **deployment's completion target**: the operator's own receiver, `COMPLETION_CALLBACK_URL`,
   receives the completion notice, whose `error` is the run's problem in the operator's view.

Each webhook carries exactly the synchronous body in its view, but for `status`, the HTTP envelope's
member, which a webhook POST does not have. A client branching on `code`, `retry` or `next_step` must
not read one answer synchronously and another over a webhook, and a caller must never receive over a
webhook the diagnostics its synchronous view withholds, even when an operator's key started the run.
"""

import asyncio
import json
import os
from collections.abc import Callable
from typing import Any, cast

import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from mthds.protocol.problem.registry import CoreCode
from pipelex.base_exceptions import PipelexConfigError, PipelexError
from pipelex.errors.problem import ProblemView
from pipelex.pipe_run import caller_webhook_delivery as caller_webhook_delivery_module
from pipelex.pipe_run import delivery_executor as delivery_executor_module
from pipelex.pipe_run.caller_webhook_delivery import CALLER_WEBHOOK_SECRET_ENV
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, DeliveryStatus
from pipelex.pipe_run.delivery_executor import DeliveryExecutor
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.plugins.orchestrator_registry import OrchestratorRegistry
from pipelex.runtime_bridge.payloads import PipelexPipeDispatchAck, PipelexPipeRunOutput
from pytest_mock import MockerFixture

from pipelex_api.api_config import ApiConfig
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.problem_view import mark_operator_request
from pipelex_api.routes import router as api_router
from pipelex_api.run_webhooks import COMPLETION_CALLBACK_URL_ENV
from tests.unit._constants import VALID_MTHDS
from tests.unit.test_data import ProblemTestData, rate_limited_failure

_PIPELINE_NS = "pipelex_api.routes.pipelex.pipeline"
_MODE = "temporal"
_RUN_ID = "run-webhook-view-1"
_COMPLETION_URL = ProblemTestData.COMPLETION_TARGET_TEMPLATE.format(pipeline_run_id=_RUN_ID)


def _config_failure() -> PipelexError:
    """An operator's fault, whose step differs between the views and whose message only the operator reads."""
    return PipelexConfigError("the gateway config is missing")


# The failures the two paths are compared on, by id: the problem with the most members, and the operator's fault.
_FAILURES: dict[str, Callable[[], PipelexError]] = {
    "provider_rate_limit": rate_limited_failure,
    "operator_configuration": _config_failure,
}


class _RecordingOrchestrator:
    """An async-capable orchestrator that records the delivery assignment of every run it is handed."""

    supports_fire_and_forget = True

    def __init__(self) -> None:
        self.delivery_assignments: list[DeliveryAssignment | None] = []

    async def execute(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeRunOutput:  # noqa: ARG002
        msg = "These tests dispatch through /start only."
        raise AssertionError(msg)

    async def start(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeDispatchAck:  # noqa: ARG002
        self.delivery_assignments.append(delivery_assignment)
        return PipelexPipeDispatchAck(pipeline_run_id=_RUN_ID, workflow_id="wf-webhook-view-1")


def _router_dependencies(view: ProblemView) -> list[Any]:
    """What authentication leaves on a request of `view`: the operator's mark, or nothing for a caller."""
    match view:
        case ProblemView.OPERATOR:
            return [Depends(mark_operator_request)]
        case ProblemView.CALLER:
            return []


def _start_with_a_callback(mocker: MockerFixture, *, view: ProblemView) -> DeliveryAssignment:
    """Start a run with a caller webhook on a deployment with a completion target, as a request of `view`; return its assignment."""
    mocker.patch.dict(
        os.environ,
        {
            "COMPLETION_CALLBACK_SECRET": ProblemTestData.SYNTHETIC_CALLBACK_SECRET,
            COMPLETION_CALLBACK_URL_ENV: ProblemTestData.COMPLETION_TARGET_TEMPLATE,
            CALLER_WEBHOOK_SECRET_ENV: ProblemTestData.SYNTHETIC_CALLER_WEBHOOK_SECRET,
        },
    )
    mocker.patch(f"{_PIPELINE_NS}.get_api_config", return_value=ApiConfig(orchestration_mode=_MODE, allow_request_orchestration_mode_override=False))
    orchestrator = _RecordingOrchestrator()
    mocker.patch(f"{_PIPELINE_NS}.get_orchestrator_registry", return_value=OrchestratorRegistry({_MODE: orchestrator}))
    app = FastAPI()
    app.include_router(api_router, prefix="/v1", dependencies=_router_dependencies(view))
    register_exception_handlers(app)

    response = TestClient(app).post(
        "/v1/start",
        json={
            "pipe_code": "echo",
            "mthds_contents": [VALID_MTHDS],
            "inputs": {"text": "hello"},
            "pipeline_run_id": _RUN_ID,
            "callback_urls": [ProblemTestData.CALLBACK_URL],
        },
    )

    assert response.status_code == 202, response.text
    (delivery_assignment,) = orchestrator.delivery_assignments
    assert delivery_assignment is not None
    return delivery_assignment


def _synchronous_body(*, failure: Callable[[], PipelexError], view: ProblemView) -> dict[str, Any]:
    """The body the synchronous path answers `failure` with, to a request of `view`."""
    router = APIRouter()

    async def fail() -> None:
        raise failure()

    router.add_api_route("/fail", fail, methods=["GET"])
    app = FastAPI()
    app.include_router(router, dependencies=_router_dependencies(view))
    register_exception_handlers(app)
    body = TestClient(app).get("/fail").json()
    return cast("dict[str, Any]", body)


def _posted_failure(mocker: MockerFixture, *, delivery_assignment: DeliveryAssignment, failure: PipelexError) -> dict[str, dict[str, Any]]:
    """Deliver `failure` as the run's outcome to the assignment's webhooks, and return the body each receiver got, by URL."""
    received: dict[str, dict[str, Any]] = {}

    def receiver(request: httpx.Request) -> httpx.Response:
        received[str(request.url)] = json.loads(request.content)
        return httpx.Response(200)

    mocker.patch.object(delivery_executor_module, "SsrfGuardedTransport", return_value=httpx.MockTransport(receiver))
    mocker.patch.object(caller_webhook_delivery_module, "SsrfGuardedTransport", return_value=httpx.MockTransport(receiver))

    asyncio.run(
        DeliveryExecutor().execute(
            None,
            storage_scope="webhook-view-scope",
            pipeline_run_id=_RUN_ID,
            delivery_assignment=delivery_assignment.model_copy(update={"storage": None}),
            status=DeliveryStatus.FAILED,
            # A failed run's problem reaches the delivery in the operator's view; each webhook takes its own.
            problem=failure.to_problem(view=ProblemView.OPERATOR),
        )
    )

    assert set(received) == {_COMPLETION_URL, ProblemTestData.CALLBACK_URL}
    return received


class TestWebhookRecoveryCrossPath:
    @pytest.mark.parametrize("view", [ProblemView.OPERATOR, ProblemView.CALLER])
    def test_each_hop_reads_its_own_view_whoever_started_the_run(self, mocker: MockerFixture, view: ProblemView) -> None:
        """The caller's webhook reads the caller's view and the deployment's target the operator's, whatever the request's view."""
        delivery_assignment = _start_with_a_callback(mocker, view=view)

        (completion_target,) = delivery_assignment.webhooks
        assert completion_target.url == _COMPLETION_URL
        assert completion_target.problem_view == ProblemView.OPERATOR
        assert [caller_webhook.url for caller_webhook in delivery_assignment.caller_webhooks] == [ProblemTestData.CALLBACK_URL]

    @pytest.mark.parametrize("view", [ProblemView.OPERATOR, ProblemView.CALLER])
    @pytest.mark.parametrize("failure_id", list(_FAILURES))
    def test_each_hop_receives_the_synchronous_answer_in_its_view(self, mocker: MockerFixture, view: ProblemView, failure_id: str) -> None:
        failure = _FAILURES[failure_id]
        delivery_assignment = _start_with_a_callback(mocker, view=view)

        received = _posted_failure(mocker, delivery_assignment=delivery_assignment, failure=failure())

        event = received[ProblemTestData.CALLBACK_URL]
        assert event["type"] == "run.finished"
        assert event["data"]["pipeline_run_id"] == _RUN_ID
        assert event["data"]["status"] == "failed"
        caller_body = _synchronous_body(failure=failure, view=ProblemView.CALLER)
        # `status` is the HTTP envelope's member: the synchronous body carries it, no webhook's error does.
        assert event["data"]["error"] == {member: value for member, value in caller_body.items() if member != "status"}
        assert "diagnostics" not in event["data"]["error"]
        notice = received[_COMPLETION_URL]
        assert notice["pipeline_run_id"] == _RUN_ID
        assert notice["state"] == DeliveryStatus.FAILED
        operator_body = _synchronous_body(failure=failure, view=ProblemView.OPERATOR)
        assert notice["error"] == {member: value for member, value in operator_body.items() if member != "status"}
        assert "diagnostics" in notice["error"]

    def test_a_caller_never_receives_the_diagnostics_over_the_webhook(self, mocker: MockerFixture) -> None:
        """What the caller's synchronous view withholds, the provider's own answer included, its webhook withholds too, even
        when an operator's key started the run.
        """
        delivery_assignment = _start_with_a_callback(mocker, view=ProblemView.OPERATOR)

        received = _posted_failure(mocker, delivery_assignment=delivery_assignment, failure=rate_limited_failure())

        posted_error = received[ProblemTestData.CALLBACK_URL]["data"]["error"]
        assert posted_error["code"] == CoreCode.PROVIDER_RATE_LIMITED
        assert posted_error["detail"] == ProblemTestData.RATE_LIMIT_DETAIL
        for operator_only in (ProblemTestData.RATE_LIMIT_MESSAGE, ProblemTestData.RATE_LIMIT_PROVIDER_REQUEST_ID, "LLMCompletionError"):
            assert operator_only not in str(posted_error), operator_only
