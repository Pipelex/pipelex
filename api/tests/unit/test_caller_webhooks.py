"""The runner's two webhook hops on `/execute` and `/start`: the caller's `callback_urls` and the deployment's completion target.

A caller's URL receives the signed `run.finished` event of the caller-webhook contract, under the secret the runner's
operator configures in `CALLER_WEBHOOK_SECRET`, so a request carrying any is refused with a 422 naming that setting on a
runner whose operator configured none, before its method is fetched, written or run. `/execute` honors `callback_urls`
and a caller's `pipeline_run_id` as `/start` does. The deployment's completion target, `COMPLETION_CALLBACK_URL`, is a
different hop: a URL equal to it among the `callback_urls` is the host forwarding its own hop, never a caller's webhook.
"""

import asyncio
import json
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mthds.protocol.problem.registry import CoreCode
from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.interpreter_hub import get_pipeline_manager
from pipelex.pipe_run import caller_webhook_delivery as caller_webhook_delivery_module
from pipelex.pipe_run.caller_webhook_delivery import CALLER_WEBHOOK_SECRET_ENV
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, DeliveryStatus
from pipelex.pipe_run.delivery_executor import DeliveryExecutor
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.plugins.orchestrator_registry import OrchestratorRegistry
from pipelex.runtime_bridge.payloads import PipelexPipeDispatchAck, PipelexPipeRunOutput
from pipelex.runtime_bridge.serialization import serialize_completed_output
from pytest_mock import MockerFixture

from pipelex_api.api_config import ApiConfig
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.exceptions import RunnerMisconfiguredError
from pipelex_api.routes import router as api_router
from pipelex_api.routes.pipelex import pipeline as pipeline_module
from pipelex_api.routes.pipelex.pipeline import ApiRunner
from pipelex_api.run_webhooks import (
    COMPLETION_CALLBACK_SECRET_ENV,
    COMPLETION_CALLBACK_URL_ENV,
    completion_callback_template,
    completion_callback_url,
    start_caller_webhook_urls,
    start_delivery_assignment,
)
from tests.unit._constants import VALID_MTHDS
from tests.unit._problems import assert_problem
from tests.unit.test_data import ProblemTestData

_PIPELINE_NS = "pipelex_api.routes.pipelex.pipeline"
_CALLER_URL = "https://hooks.example.com/runs?token=caller-s3cr3t"
_RUN_ID = "client-chosen-run-0001"


class _DeliveringOrchestrator:
    """An orchestrator whose blocking arm echoes the job's input as its output and runs the real delivery it is handed.

    Its fire-and-forget arm records the assignment and acknowledges, as an async-capable backend would.
    """

    supports_fire_and_forget = True

    def __init__(self) -> None:
        self.jobs: list[PipeJob] = []
        self.delivery_assignments: list[DeliveryAssignment | None] = []

    async def execute(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeRunOutput:
        self.jobs.append(pipe_job)
        self.delivery_assignments.append(delivery_assignment)
        working_memory = pipe_job.get_working_memory()
        working_memory.set_alias(alias=MAIN_STUFF_NAME, target=next(iter(working_memory.root)))
        pipe_output = PipeOutput(working_memory=working_memory, pipeline_run_id=pipe_job.job_metadata.run_metadata.pipeline_run_id)
        if delivery_assignment is not None:
            await DeliveryExecutor().execute(
                pipe_output=pipe_output,
                storage_scope="caller-webhooks-scope",
                pipeline_run_id=pipe_job.job_metadata.run_metadata.pipeline_run_id,
                delivery_assignment=delivery_assignment,
                status=DeliveryStatus.COMPLETED,
            )
        return serialize_completed_output(pipe_output=pipe_output, workflow_id=None)

    async def start(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeDispatchAck:
        self.jobs.append(pipe_job)
        self.delivery_assignments.append(delivery_assignment)
        return PipelexPipeDispatchAck(pipeline_run_id=pipe_job.job_metadata.run_metadata.pipeline_run_id, workflow_id="wf-caller-webhooks")


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


def _register(mocker: MockerFixture, *, mode: str = "direct") -> _DeliveringOrchestrator:
    orchestrator = _DeliveringOrchestrator()
    mocker.patch(f"{_PIPELINE_NS}.get_api_config", return_value=ApiConfig(orchestration_mode=mode, allow_request_orchestration_mode_override=False))
    mocker.patch(f"{_PIPELINE_NS}.get_orchestrator_registry", return_value=OrchestratorRegistry({mode: orchestrator}))
    return orchestrator


def _receive_caller_events(mocker: MockerFixture) -> list[httpx.Request]:
    """Route the caller webhooks' calls to an in-test receiver that acknowledges each one, and record them."""
    received: list[httpx.Request] = []

    def receiver(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(204)

    mocker.patch.object(caller_webhook_delivery_module, "SsrfGuardedTransport", return_value=httpx.MockTransport(receiver))
    return received


def _run_body(**extensions: Any) -> dict[str, Any]:
    return {"pipe_code": "echo", "mthds_contents": [VALID_MTHDS], "inputs": {"text": "hello"}, **extensions}


class TestCallerWebhooks:
    @pytest.mark.parametrize("path", ["/v1/execute", "/v1/start"])
    def test_callback_urls_without_a_secret_are_refused_before_anything_runs(self, mocker: MockerFixture, path: str) -> None:
        """No secret, no caller webhook: a 422 naming the setting, and the method is never fetched nor written."""
        run_source_spy = mocker.patch(f"{_PIPELINE_NS}._run_source")

        response = _client().post(path, json=_run_body(callback_urls=[_CALLER_URL]))

        problem = assert_problem(response, status=422, code=PipelexErrorCode.WEBHOOK_SECRET_NOT_CONFIGURED)
        assert problem["params"] == {"setting": CALLER_WEBHOOK_SECRET_ENV}
        assert problem["location"] == {"field": "callback_urls"}
        assert problem["retry"] == "no"
        run_source_spy.assert_not_called()

    @pytest.mark.parametrize("path", ["/v1/execute", "/v1/start"])
    def test_a_secret_that_is_not_a_whsec_secret_is_the_operators_fault(self, mocker: MockerFixture, path: str) -> None:
        """A malformed secret is the runner's misconfiguration, a 500 whose component the caller never reads."""
        mocker.patch.dict("os.environ", {CALLER_WEBHOOK_SECRET_ENV: "not-a-signing-secret"})
        run_source_spy = mocker.patch(f"{_PIPELINE_NS}._run_source")

        response = _client().post(path, json=_run_body(callback_urls=[_CALLER_URL]))

        problem = assert_problem(response, status=500, code=CoreCode.RUNTIME_MISCONFIGURED)
        assert "component" not in problem.get("params", {})
        assert "not-a-signing-secret" not in response.text
        run_source_spy.assert_not_called()

    def test_execute_without_callback_urls_needs_no_secret(self, mocker: MockerFixture) -> None:
        orchestrator = _register(mocker)

        response = _client().post("/v1/execute", json=_run_body())

        assert response.status_code == 200, response.text
        assert orchestrator.delivery_assignments == [None]

    def test_execute_honours_the_callers_run_id_and_sends_each_callback_url_the_signed_event(self, mocker: MockerFixture) -> None:
        """A blocking `/execute` runs under the caller's id and sends its event before it answers, signed under the secret."""
        mocker.patch.dict("os.environ", {CALLER_WEBHOOK_SECRET_ENV: ProblemTestData.SYNTHETIC_CALLER_WEBHOOK_SECRET})
        orchestrator = _register(mocker)
        received = _receive_caller_events(mocker)

        response = _client().post("/v1/execute", json=_run_body(pipeline_run_id=_RUN_ID, callback_urls=[_CALLER_URL]))

        assert response.status_code == 200, response.text
        assert response.json()["pipeline_run_id"] == _RUN_ID
        (job,) = orchestrator.jobs
        assert job.job_metadata.run_metadata.pipeline_run_id == _RUN_ID
        (delivery_assignment,) = orchestrator.delivery_assignments
        assert delivery_assignment is not None
        # An `/execute` run answers with its output: nothing is stored and no completion target is notified.
        assert delivery_assignment.storage is None
        assert delivery_assignment.webhooks == []
        assert [target.url for target in delivery_assignment.caller_webhooks] == [_CALLER_URL]
        (call,) = received
        assert str(call.url) == _CALLER_URL
        event = json.loads(call.content)
        assert event["type"] == "run.finished"
        assert event["data"] == {"pipeline_run_id": _RUN_ID, "status": "completed"}
        assert call.headers["webhook-id"] == delivery_assignment.caller_webhooks[0].delivery_id
        assert "x-completion-signature" not in call.headers

    def test_execute_refuses_a_run_id_still_in_flight(self, mocker: MockerFixture) -> None:
        """A caller's id already registered for a run in flight is a 409, as on `/start`."""
        _register(mocker)
        get_pipeline_manager().add_new_pipeline(pipe_code=None, pipeline_run_id=_RUN_ID)
        try:
            response = _client().post("/v1/execute", json=_run_body(pipeline_run_id=_RUN_ID))
        finally:
            get_pipeline_manager().remove_pipeline(pipeline_run_id=_RUN_ID)

        assert_problem(response, status=409, code=PipelexErrorCode.RUN_ALREADY_EXISTS)

    def test_a_receiver_s_failure_never_changes_the_execute_answer(self, mocker: MockerFixture) -> None:
        """A caller webhook that cannot be delivered is the delivery's failure: the run's answer stands."""
        mocker.patch.dict("os.environ", {CALLER_WEBHOOK_SECRET_ENV: ProblemTestData.SYNTHETIC_CALLER_WEBHOOK_SECRET})
        _register(mocker)
        mocker.patch.object(
            caller_webhook_delivery_module, "SsrfGuardedTransport", return_value=httpx.MockTransport(lambda _request: httpx.Response(503))
        )
        mocker.patch.object(caller_webhook_delivery_module, "sleep", new=mocker.AsyncMock())

        response = _client().post("/v1/execute", json=_run_body(callback_urls=[_CALLER_URL]))

        assert response.status_code == 200, response.text
        assert response.json()["state"] == "COMPLETED"

    def test_the_hosts_completion_url_among_callback_urls_is_the_deployments_hop(self, mocker: MockerFixture) -> None:
        """A host forwarding its completion URL needs no caller secret: the URL is notified once, as the completion target."""
        mocker.patch.dict(
            "os.environ",
            {
                COMPLETION_CALLBACK_URL_ENV: ProblemTestData.COMPLETION_TARGET_TEMPLATE,
                COMPLETION_CALLBACK_SECRET_ENV: ProblemTestData.SYNTHETIC_CALLBACK_SECRET,
            },
        )
        orchestrator = _register(mocker, mode="temporal")
        completion_url = ProblemTestData.COMPLETION_TARGET_TEMPLATE.format(pipeline_run_id=_RUN_ID)

        response = _client().post("/v1/start", json=_run_body(pipeline_run_id=_RUN_ID, callback_urls=[completion_url]))

        assert response.status_code == 202, response.text
        (delivery_assignment,) = orchestrator.delivery_assignments
        assert delivery_assignment is not None
        (completion_target,) = delivery_assignment.webhooks
        assert completion_target.url == completion_url
        assert set(completion_target.headers) == {"X-Completion-Signature"}
        assert delivery_assignment.caller_webhooks == []

    def test_on_execute_the_completion_url_is_a_callers_webhook(self, mocker: MockerFixture) -> None:
        """An `/execute` run notifies no completion target, so the target's URL among its `callback_urls` is sent the caller's event."""
        mocker.patch.dict(
            "os.environ",
            {
                COMPLETION_CALLBACK_URL_ENV: ProblemTestData.COMPLETION_TARGET_TEMPLATE,
                COMPLETION_CALLBACK_SECRET_ENV: ProblemTestData.SYNTHETIC_CALLBACK_SECRET,
                CALLER_WEBHOOK_SECRET_ENV: ProblemTestData.SYNTHETIC_CALLER_WEBHOOK_SECRET,
            },
        )
        orchestrator = _register(mocker)
        received = _receive_caller_events(mocker)
        completion_url = ProblemTestData.COMPLETION_TARGET_TEMPLATE.format(pipeline_run_id=_RUN_ID)

        response = _client().post("/v1/execute", json=_run_body(pipeline_run_id=_RUN_ID, callback_urls=[completion_url]))

        assert response.status_code == 200, response.text
        (delivery_assignment,) = orchestrator.delivery_assignments
        assert delivery_assignment is not None
        assert delivery_assignment.webhooks == []
        assert [target.url for target in delivery_assignment.caller_webhooks] == [completion_url]
        (call,) = received
        assert str(call.url) == completion_url
        assert json.loads(call.content)["type"] == "run.finished"
        assert "x-completion-signature" not in call.headers

    def test_start_without_a_completion_target_notifies_only_the_callers_urls(self, mocker: MockerFixture) -> None:
        """No `COMPLETION_CALLBACK_URL`, no completion target: every `callback_urls` entry is the caller's, signed as such."""
        mocker.patch.dict("os.environ", {CALLER_WEBHOOK_SECRET_ENV: ProblemTestData.SYNTHETIC_CALLER_WEBHOOK_SECRET})
        orchestrator = _register(mocker, mode="temporal")

        response = _client().post("/v1/start", json=_run_body(callback_urls=[_CALLER_URL, _CALLER_URL]))

        assert response.status_code == 202, response.text
        (delivery_assignment,) = orchestrator.delivery_assignments
        assert delivery_assignment is not None
        assert delivery_assignment.webhooks == []
        # A URL listed twice is one delivery.
        assert [target.url for target in delivery_assignment.caller_webhooks] == [_CALLER_URL]
        assert delivery_assignment.storage is not None

    @pytest.mark.parametrize(
        "configured",
        [
            pytest.param("ops.example.com/runs", id="no_scheme"),
            pytest.param("ftp://ops.example.com/runs", id="not_http"),
            pytest.param("https:///runs", id="no_host"),
            pytest.param("https://ops.example.com/runs#done", id="fragment"),
            pytest.param("https://ops.example.com/{pipeline_run_id}/{pipeline_run_id}", id="placeholder_twice"),
            pytest.param("https://{pipeline_run_id}/complete", id="placeholder_as_host"),
            pytest.param("https://ops.example.com{pipeline_run_id}/complete", id="placeholder_in_host"),
            pytest.param("https://{pipeline_run_id}@ops.example.com/complete", id="placeholder_as_user"),
            pytest.param("https://ops.example.com:{pipeline_run_id}/complete", id="placeholder_as_port"),
            pytest.param("{pipeline_run_id}://ops.example.com/complete", id="placeholder_as_scheme"),
        ],
    )
    def test_a_malformed_completion_target_is_refused(self, monkeypatch: pytest.MonkeyPatch, configured: str) -> None:
        """A completion target that is not one absolute http or https URL stops the boot and fails the run naming the variable."""
        monkeypatch.setenv(COMPLETION_CALLBACK_URL_ENV, configured)

        with pytest.raises(RunnerMisconfiguredError) as exc_info:
            completion_callback_template()

        assert exc_info.value.component == COMPLETION_CALLBACK_URL_ENV

    @pytest.mark.parametrize(
        "configured",
        [
            pytest.param("https://ops.example.com/runs/complete/{pipeline_run_id}", id="in_path"),
            pytest.param("https://ops.example.com/runs/complete?run={pipeline_run_id}", id="in_query"),
            pytest.param("https://ops.example.com/runs/complete", id="none"),
        ],
    )
    def test_the_placeholder_may_sit_in_the_path_or_the_query(self, monkeypatch: pytest.MonkeyPatch, configured: str) -> None:
        monkeypatch.setenv(COMPLETION_CALLBACK_URL_ENV, configured)

        assert completion_callback_template() == configured

    @pytest.mark.parametrize(
        "forwarded_url",
        [
            pytest.param("https://ops.example.com/runs/complete/order 42", id="id_as_it_is"),
            pytest.param("https://ops.example.com/runs/complete/order%2042", id="id_percent_encoded"),
            pytest.param("HTTPS://OPS.example.com/runs/complete/order%2042", id="scheme_and_host_in_capitals"),
        ],
    )
    def test_the_forwarded_completion_url_is_recognised_however_its_id_is_written(self, monkeypatch: pytest.MonkeyPatch, forwarded_url: str) -> None:
        """The target's URL holds the id percent-encoded, and a host forwarding it may not: both name the same hop."""
        monkeypatch.setenv(COMPLETION_CALLBACK_URL_ENV, ProblemTestData.COMPLETION_TARGET_TEMPLATE)
        monkeypatch.setenv(COMPLETION_CALLBACK_SECRET_ENV, ProblemTestData.SYNTHETIC_CALLBACK_SECRET)

        assert start_caller_webhook_urls(callback_urls=[forwarded_url, _CALLER_URL], pipeline_run_id="order 42") == [_CALLER_URL]
        delivery_assignment = start_delivery_assignment(caller_urls=[forwarded_url, _CALLER_URL], pipeline_run_id="order 42")
        assert [target.url for target in delivery_assignment.webhooks] == ["https://ops.example.com/runs/complete/order%2042"]
        assert [target.url for target in delivery_assignment.caller_webhooks] == [_CALLER_URL]

    def test_the_run_id_is_percent_encoded_into_the_completion_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An id the caller chose fills its placeholder as one path segment, never adding a segment or a query."""
        monkeypatch.setenv(COMPLETION_CALLBACK_URL_ENV, ProblemTestData.COMPLETION_TARGET_TEMPLATE)

        assert completion_callback_url(pipeline_run_id="run/../x?y") == "https://ops.example.com/runs/complete/run%2F..%2Fx%3Fy"
        assert completion_callback_url(pipeline_run_id=None) is None

    @pytest.mark.parametrize(
        ("configured_url", "configured_secret", "refused_setting"),
        [
            pytest.param("not a url", ProblemTestData.SYNTHETIC_CALLBACK_SECRET, COMPLETION_CALLBACK_URL_ENV, id="malformed_url"),
            pytest.param(ProblemTestData.COMPLETION_TARGET_TEMPLATE, "", COMPLETION_CALLBACK_SECRET_ENV, id="no_secret"),
        ],
    )
    def test_the_server_boot_checks_the_completion_target(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, configured_url: str, configured_secret: str, refused_setting: str
    ) -> None:
        """A malformed completion target, or one without its signing secret, stops the server at boot, before any request is served."""
        # Imported in-test, as the conformance suite imports the app, so a bad env var fails this test, not the collection.
        from pipelex_api.main import lifespan  # noqa: PLC0415

        monkeypatch.setenv(COMPLETION_CALLBACK_URL_ENV, configured_url)
        monkeypatch.setenv(COMPLETION_CALLBACK_SECRET_ENV, configured_secret)
        pipelex_make_spy = mocker.patch("pipelex_api.main.Pipelex.make")

        async def boot() -> None:
            async with lifespan(FastAPI()):
                pass

        with pytest.raises(RunnerMisconfiguredError) as exc_info:
            asyncio.run(boot())
        assert exc_info.value.component == refused_setting
        pipelex_make_spy.assert_not_called()

    def test_a_completion_target_without_its_secret_refuses_start_before_anything_runs(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A completion target the server cannot sign is the operator's fault, answered before the method is fetched or set up."""
        monkeypatch.setenv(COMPLETION_CALLBACK_URL_ENV, ProblemTestData.COMPLETION_TARGET_TEMPLATE)
        monkeypatch.setenv(COMPLETION_CALLBACK_SECRET_ENV, "")
        _register(mocker, mode="temporal")
        run_source_spy = mocker.patch(f"{_PIPELINE_NS}._run_source")

        response = _client().post("/v1/start", json=_run_body())

        problem = assert_problem(response, status=500, code=CoreCode.RUNTIME_MISCONFIGURED)
        assert "component" not in problem.get("params", {})
        run_source_spy.assert_not_called()

    def test_the_runner_checks_the_completion_target_before_it_sets_a_run_up(self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
        """An in-process caller of the runner meets the same check, before `pipeline_run_setup` registers anything."""
        monkeypatch.setenv(COMPLETION_CALLBACK_URL_ENV, ProblemTestData.COMPLETION_TARGET_TEMPLATE)
        monkeypatch.setenv(COMPLETION_CALLBACK_SECRET_ENV, "")
        _register(mocker, mode="temporal")
        setup_spy = mocker.patch(f"{_PIPELINE_NS}.pipeline_run_setup")

        with pytest.raises(RunnerMisconfiguredError) as exc_info:
            asyncio.run(ApiRunner().start(pipe_code="echo", mthds_contents=[VALID_MTHDS], inputs={"text": "hello"}))

        assert exc_info.value.component == COMPLETION_CALLBACK_SECRET_ENV
        setup_spy.assert_not_called()

    def test_a_run_whose_dispatch_fails_gives_its_id_back(self, mocker: MockerFixture) -> None:
        """A run set up but never handed over is released, so the caller can start it again under the same id."""
        orchestrator = _register(mocker, mode="temporal")
        dispatch_error = PipelexUnexpectedError("The orchestrator could not enqueue the run.")
        mocker.patch.object(orchestrator, "start", new=mocker.AsyncMock(side_effect=dispatch_error))
        release_spy = mocker.spy(pipeline_module, "release_run_setup")

        response = _client().post("/v1/start", json=_run_body(pipeline_run_id=_RUN_ID))

        assert_problem(response, status=500, code=CoreCode.RUNTIME_UNEXPECTED)
        release_spy.assert_called_once()
        # The id is free again: registering it does not collide with a run left behind.
        get_pipeline_manager().add_new_pipeline(pipe_code=None, pipeline_run_id=_RUN_ID)
        get_pipeline_manager().remove_pipeline(pipeline_run_id=_RUN_ID)
