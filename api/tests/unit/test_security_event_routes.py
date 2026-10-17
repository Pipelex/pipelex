"""A security refusal answered by the run routes fails under its security code and logs one security event naming the request.

`/execute` runs through the base runner, whose own boundary reports a refusal before the run; `/start` builds its job
itself, so a refusal before its run reaches the global handler unreported, which reports it there. Either way the event
is logged once, with the run's extras the body carried and the request id, and never what was refused.
"""

import io
import json
import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mthds.protocol.problem.registry import CoreCode
from pipelex.errors.security_event import SECURITY_EVENT_MESSAGE, SECURITY_EVENT_NAME
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.plugins.orchestrator_registry import OrchestratorRegistry
from pipelex.runtime_bridge.payloads import PipelexPipeDispatchAck, PipelexPipeRunOutput
from pipelex.tools.log.json_log_sink import JsonLogSink
from pytest_mock import MockerFixture

from pipelex_api.api_config import ApiConfig
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.middleware import REQUEST_ID_HEADER, RequestIdMiddleware
from pipelex_api.routes import router as api_router

_PIPELINE_NS = "pipelex_api.routes.pipelex.pipeline"
_MODE = "temporal"
_SECURITY_EVENT_LOGGER = "pipelex.errors.security_event"
_LOCAL_PATH = "/etc/passwd"
_REQUEST_ID = "req-security-event-1"
_DESCRIBE_IMAGE_MTHDS = """\
domain = "security_event"
main_pipe = "describe_image"

[pipe.describe_image]
type = "PipeLLM"
description = "Describe an image"
inputs = { photo = "Image" }
output = "Text"
prompt = "Describe this image. $photo"
"""


class _UnreachedOrchestrator:
    """An async-capable orchestrator no refused request reaches, so a route refusing before the run dispatches nothing."""

    supports_fire_and_forget = True

    async def execute(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeRunOutput:  # noqa: ARG002
        msg = "a refused request must not reach the orchestrator"
        raise AssertionError(msg)

    async def start(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeDispatchAck:  # noqa: ARG002
        msg = "a refused request must not reach the orchestrator"
        raise AssertionError(msg)


def _build_client(mocker: MockerFixture) -> TestClient:
    config = ApiConfig(orchestration_mode=_MODE, allow_request_orchestration_mode_override=False)
    mocker.patch(f"{_PIPELINE_NS}.get_api_config", return_value=config)
    mocker.patch(f"{_PIPELINE_NS}.get_orchestrator_registry", return_value=OrchestratorRegistry({_MODE: _UnreachedOrchestrator()}))
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(RequestIdMiddleware(app))


@contextmanager
def _security_event_lines() -> Generator[list[dict[str, Any]]]:
    """The security events logged in the block, as the `json` sink the server selects serializes them."""
    buffer = io.StringIO()
    handler = JsonLogSink(stream=buffer).handler
    logger = logging.getLogger(_SECURITY_EVENT_LOGGER)
    previous_level = logger.level
    logger.setLevel(logging.WARNING)
    logger.addHandler(handler)
    lines: list[dict[str, Any]] = []
    try:
        yield lines
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        handler.close()
        lines.extend(json.loads(line) for line in buffer.getvalue().splitlines() if line)


class TestSecurityEventRoutes:
    @pytest.mark.parametrize(
        ("route", "pipeline_run_id"),
        [
            pytest.param("/v1/execute", None, id="execute"),
            pytest.param("/v1/start", "run-security-event-1", id="start"),
        ],
    )
    def test_a_refused_input_answers_its_security_code_and_logs_one_event(
        self, mocker: MockerFixture, route: str, pipeline_run_id: str | None
    ) -> None:
        client = _build_client(mocker)
        body: dict[str, Any] = {
            "mthds_contents": [_DESCRIBE_IMAGE_MTHDS],
            "inputs": {"photo": _LOCAL_PATH},
            "storage_scope": "org_abc/mt_1/run_1",
            "read_scope": "org_abc",
            "analytics_groups": {"org_id": "org_abc"},
        }
        if pipeline_run_id is not None:
            body["pipeline_run_id"] = pipeline_run_id

        with _security_event_lines() as lines:
            response = client.post(route, json=body, headers={REQUEST_ID_HEADER: _REQUEST_ID})

        assert response.status_code == 422, response.text
        assert response.json()["code"] == CoreCode.SECURITY_INPUT_URL_REFUSED
        (line,) = lines
        assert line["message"] == SECURITY_EVENT_MESSAGE
        assert line["event.name"] == SECURITY_EVENT_NAME
        assert line["error.code"] == CoreCode.SECURITY_INPUT_URL_REFUSED
        assert line["error.domain"] == "input"
        assert line["security.target"] == "url"
        assert line["security.target_class"] == "scheme"
        assert line["run.extras.org_id"] == "org_abc"
        assert line["request_id"] == _REQUEST_ID
        assert line.get("pipeline_run_id") == pipeline_run_id
        assert _LOCAL_PATH not in json.dumps(line)
