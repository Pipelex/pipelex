"""Route-level tests for the run-source precondition on /execute and /start.

Pins the layered extension policy's Rule 4 (`conformance/specs/pipelex-platform-api.md` →
"Layered extension policy", in the `conformance` repo beside the tests that verify it): an unknown
extension key never waives the requirement that a run request carry a source
this server understands, and a source-less body whose keys this deployment does
not handle gets a message that NAMES them — so "a hosted client was pointed at
a source-available runner" reads as that, instead of as a generic precondition
failure.

The runner is mocked as in `test_pipeline_routes`; nothing here reaches inference,
because every assertion lands on a request-shape 422 raised during body parsing.
"""

from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from mthds.protocol.problem.registry import CoreCode
from pipelex.errors.problem import ProblemView, make_problem
from pipelex.pipeline.pipeline_response import PipelexRunResultStart, RunState
from pytest_mock import MockerFixture

from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.problem_view import mark_operator_request
from pipelex_api.routes.pipelex.pipeline import router as pipeline_router
from tests.unit._constants import VALID_MTHDS

_BASE_PRECONDITION_FRAGMENT = "pipe_code and mthds_contents cannot both be empty"


def _build_client(mocker: MockerFixture, *, as_operator: bool = False) -> tuple[TestClient, Any]:
    """Wire a FastAPI app whose pipeline runner is fully mocked; return (client, runner_mock).

    The whole runner comes back rather than just `execute`, because `/v1/start` dispatches
    through `runner.start`: a test that asserts only on `execute` pins nothing on that route.
    `as_operator` marks each request as the operator's, whose view carries the refusal's own message
    in `diagnostics`.
    """
    app = FastAPI()
    app.include_router(pipeline_router, prefix="/v1", dependencies=[Depends(mark_operator_request)] if as_operator else [])
    register_exception_handlers(app)

    fake_execute_response = mocker.MagicMock()
    fake_execute_response.model_dump.return_value = {
        "pipeline_run_id": "test-run-1",
        "state": "COMPLETED",
        "pipe_output": {"working_memory": {"root": {}, "aliases": {}}},
    }
    fake_runner = mocker.MagicMock()
    fake_runner.execute = mocker.AsyncMock(return_value=fake_execute_response)
    fake_runner.start = mocker.AsyncMock(
        return_value=PipelexRunResultStart(
            pipeline_run_id="test-run-1",
            created_at="2026-01-15T12:00:00Z",
            state=RunState.STARTED,
            workflow_id="wf-1",
        )
    )
    mocker.patch("pipelex_api.routes.pipelex.pipeline.ApiRunner", return_value=fake_runner)
    return TestClient(app), fake_runner


def _assert_request_refusal(response: Any, *, code: CoreCode, params: dict[str, Any]) -> dict[str, Any]:
    """Assert a request-shape 422 under `code`, its caller sentences rendered from `params`, and return its body."""
    assert response.status_code == 422, response.text
    assert response.headers["content-type"] == "application/problem+json"
    problem: dict[str, Any] = response.json()
    caller_problem = make_problem(code=code, view=ProblemView.CALLER, params=params)
    assert problem["code"] == code
    assert problem["type"] == f"https://mthds.ai/errors/{code}"
    assert problem["status"] == 422
    assert problem["domain"] == "input"
    assert problem.get("params") == params
    assert problem["detail"] == caller_problem.detail
    return problem


class TestRunSourcePrecondition:
    """A run source is required; extension args never waive it, and they are named when they are all the body has."""

    @pytest.mark.parametrize("route", ["/v1/execute", "/v1/start"])
    def test_extension_only_body_is_refused_and_names_the_unhandled_keys(self, mocker: MockerFixture, route: str):
        # The hosted catalog selector resolved on the platform and never crosses down to a
        # runner (Rule 3), so a body carrying it alone means a hosted client reached the
        # wrong deployment. The 422 must diagnose exactly that, by name.
        client, runner = _build_client(mocker, as_operator=True)
        response = client.post(route, json={"method_id": "mt_abc123"})
        # The runtime's own refusal of a field this runner does not take: `request.unsupported`, naming the field.
        problem = _assert_request_refusal(
            response, code=CoreCode.REQUEST_UNSUPPORTED, params={"field": "method_id", "reason": "hosted_only_extension"}
        )
        assert problem["diagnostics"]["error_class"] == "PipelexRequestError"
        message = problem["diagnostics"]["message"]
        assert "`method_id`" in message
        assert "not handled by this deployment" in message
        assert "hosted API" in message
        # The run never dispatched: this is a request-shape refusal, not a failed run.
        # Both dispatch methods are asserted because the two routes use different ones
        # (`/v1/execute` → `runner.execute`, `/v1/start` → `runner.start`).
        runner.execute.assert_not_awaited()
        runner.start.assert_not_awaited()

    def test_every_unhandled_key_is_named_sorted(self, mocker: MockerFixture):
        client, _ = _build_client(mocker, as_operator=True)
        response = client.post("/v1/execute", json={"method_id": "mt_abc123", "future_arg": "x"})
        # The caller's parameters name the first, the operator's message every one.
        problem = _assert_request_refusal(
            response, code=CoreCode.REQUEST_UNSUPPORTED, params={"field": "future_arg", "reason": "hosted_only_extension"}
        )
        assert "`future_arg`, `method_id`" in problem["diagnostics"]["message"]

    def test_empty_body_keeps_the_base_guidance(self, mocker: MockerFixture):
        # Nothing to name — the caller sent no extension at all, so the message stays the
        # one that explains what a run source IS.
        client, _ = _build_client(mocker, as_operator=True)
        response = client.post("/v1/execute", json={})
        problem = _assert_request_refusal(response, code=CoreCode.REQUEST_INVALID, params={"field": "pipe_code"})
        message = problem["diagnostics"]["message"]
        assert _BASE_PRECONDITION_FRAGMENT in message
        assert "not handled by this deployment" not in message

    def test_server_handled_extras_are_never_named_as_unhandled(self, mocker: MockerFixture):
        # `callback_urls` / `orchestration_mode` / `storage_scope` / `pipeline_run_id` ARE
        # handled here (`PipelineApiExtras`). A source-less body carrying only those is still
        # a 422, but naming them as unhandled would be a lie.
        client, _ = _build_client(mocker, as_operator=True)
        response = client.post(
            "/v1/start",
            json={"pipeline_run_id": "run-1", "callback_urls": ["https://example.com/hook"], "storage_scope": "tenant/run"},
        )
        problem = _assert_request_refusal(response, code=CoreCode.REQUEST_INVALID, params={"field": "pipe_code"})
        message = problem["diagnostics"]["message"]
        assert _BASE_PRECONDITION_FRAGMENT in message
        assert "not handled by this deployment" not in message

    @pytest.mark.parametrize(
        ("label", "body"),
        [
            ("pipe_code", {"pipe_code": "echo", "method_id": "mt_abc123", "inputs": {"text": "hi"}}),
            ("mthds_contents", {"mthds_contents": [VALID_MTHDS], "method_id": "mt_abc123", "inputs": {"text": "hi"}}),
            ("bundle_files", {"files": {"main.mthds": VALID_MTHDS}, "method_id": "mt_abc123", "inputs": {"text": "hi"}}),
        ],
    )
    def test_a_body_with_a_source_still_accepts_unknown_extensions(self, mocker: MockerFixture, label: str, body: dict[str, Any]):
        # Rule 1: the model stays extension-open. Rule 4 tightens the SOURCE-LESS case only —
        # an unknown key alongside a real run source is still forwarded untouched.
        client, runner = _build_client(mocker)
        response = client.post("/v1/execute", json=body)
        assert response.status_code == 200, f"{label}: {response.text[:300]!r}"
        runner.execute.assert_awaited_once()

    def test_legacy_singular_mthds_content_is_still_a_source(self, mocker: MockerFixture):
        # `mthds_content` (singular) is the legacy alias `from_body` folds into the plural
        # field — it is a source, so it must not be reported as an unhandled extension arg.
        client, runner = _build_client(mocker)
        response = client.post("/v1/execute", json={"mthds_content": VALID_MTHDS, "inputs": {"text": "hi"}})
        assert response.status_code == 200, response.text[:300]
        runner.execute.assert_awaited_once()
