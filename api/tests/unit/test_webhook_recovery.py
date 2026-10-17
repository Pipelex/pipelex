"""Cross-path consistency of the API's two failure surfaces.

A failure reaches a client along two paths:

1. The **synchronous HTTP path**: `POST /execute`, and every other route that lets a `PipelexError`
   propagate, answers the error's problem through `problem_response`, in the view of whoever made
   the request (`pipelex_api.problem_view`).
2. The **asynchronous webhook path**: `POST /start` builds each completion webhook's target, and on
   a failed run pipelex's `DeliveryExecutor` posts the run's problem under `error`, in the view the
   target carries (`WebhookTarget.problem_view`).

A completion webhook is the same answer as the synchronous response, delivered later, so the start
route gives each target the view of its own request, and the payload's `error` is exactly the
synchronous body in that view, but for `status`, the HTTP envelope's member, which a webhook POST
does not have. A client branching on `code`, `retry` or `next_step` must not read one answer
synchronously and another over the webhook, and a caller must never receive over a webhook the
diagnostics its synchronous view withholds.
"""

import asyncio
import os
from collections.abc import Callable
from typing import Any, cast

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from mthds.protocol.problem.registry import CoreCode
from pipelex.base_exceptions import PipelexConfigError, PipelexError
from pipelex.errors.problem import ProblemView
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
from tests.unit._constants import VALID_MTHDS
from tests.unit.test_data import ProblemTestData, rate_limited_failure

_PIPELINE_NS = "pipelex_api.routes.pipelex.pipeline"
_MODE = "temporal"
_RUN_ID = "run-webhook-view-1"


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
    """Start a run asking for a completion webhook, as a request of `view`, and return the assignment the run was handed."""
    mocker.patch.dict(os.environ, {"COMPLETION_CALLBACK_SECRET": ProblemTestData.SYNTHETIC_CALLBACK_SECRET})
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


def _posted_failure(mocker: MockerFixture, *, delivery_assignment: DeliveryAssignment, failure: PipelexError) -> dict[str, Any]:
    """Deliver `failure` as the run's outcome to the assignment's webhooks, and return the one body the webhook received."""
    mock_client = mocker.AsyncMock()
    mock_response = mocker.MagicMock()
    mock_response.raise_for_status = mocker.Mock()
    mock_client.__aenter__ = mocker.AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = mocker.AsyncMock(return_value=False)
    mock_client.post = mocker.AsyncMock(return_value=mock_response)
    mocker.patch("pipelex.pipe_run.delivery_executor.httpx.AsyncClient", return_value=mock_client)

    asyncio.run(
        DeliveryExecutor().execute(
            None,
            storage_scope="webhook-view-scope",
            pipeline_run_id=_RUN_ID,
            delivery_assignment=delivery_assignment,
            status=DeliveryStatus.FAILED,
            # A failed run's problem reaches the delivery in the operator's view; each webhook takes its own.
            problem=failure.to_problem(view=ProblemView.OPERATOR),
        )
    )

    mock_client.post.assert_awaited_once()
    post_call = mock_client.post.await_args
    assert post_call is not None
    assert post_call.args == (ProblemTestData.CALLBACK_URL,)
    payload = post_call.kwargs["json"]
    return cast("dict[str, Any]", payload)


class TestWebhookRecoveryCrossPath:
    @pytest.mark.parametrize("view", [ProblemView.OPERATOR, ProblemView.CALLER])
    def test_the_webhook_target_takes_the_start_requests_view(self, mocker: MockerFixture, view: ProblemView) -> None:
        delivery_assignment = _start_with_a_callback(mocker, view=view)

        (webhook,) = delivery_assignment.webhooks
        assert webhook.url == ProblemTestData.CALLBACK_URL
        assert webhook.problem_view == view

    @pytest.mark.parametrize("view", [ProblemView.OPERATOR, ProblemView.CALLER])
    @pytest.mark.parametrize("failure_id", list(_FAILURES))
    def test_the_failure_payload_is_the_synchronous_answer_in_the_same_view(self, mocker: MockerFixture, view: ProblemView, failure_id: str) -> None:
        failure = _FAILURES[failure_id]
        delivery_assignment = _start_with_a_callback(mocker, view=view)

        payload = _posted_failure(mocker, delivery_assignment=delivery_assignment, failure=failure())

        assert payload["pipeline_run_id"] == _RUN_ID
        assert payload["state"] == DeliveryStatus.FAILED
        synchronous_body = _synchronous_body(failure=failure, view=view)
        # `status` is the HTTP envelope's member: the synchronous body carries it, the webhook's `error` does not.
        assert "status" not in payload["error"]
        assert payload["error"] == {member: value for member, value in synchronous_body.items() if member != "status"}
        match view:
            case ProblemView.OPERATOR:
                assert "diagnostics" in payload["error"]
            case ProblemView.CALLER:
                assert "diagnostics" not in payload["error"]

    def test_a_caller_never_receives_the_diagnostics_over_the_webhook(self, mocker: MockerFixture) -> None:
        """What the caller's synchronous view withholds, the provider's own answer included, its webhook withholds too."""
        delivery_assignment = _start_with_a_callback(mocker, view=ProblemView.CALLER)

        payload = _posted_failure(mocker, delivery_assignment=delivery_assignment, failure=rate_limited_failure())

        posted_error = payload["error"]
        assert posted_error["code"] == CoreCode.PROVIDER_RATE_LIMITED
        assert posted_error["detail"] == ProblemTestData.RATE_LIMIT_DETAIL
        for operator_only in (ProblemTestData.RATE_LIMIT_MESSAGE, ProblemTestData.RATE_LIMIT_PROVIDER_REQUEST_ID, "LLMCompletionError"):
            assert operator_only not in str(posted_error), operator_only
