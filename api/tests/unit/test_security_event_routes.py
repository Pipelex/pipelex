"""A security refusal answered by the run routes fails under its security code and logs one security event naming the request.

`/execute` runs through the base runner, whose own boundary reports a refusal before the run; `/start` builds its job
itself, so a refusal before its run reaches the global handler unreported, which reports it there. A refusal the server
authors itself, a reserved object key, a callback URL aimed at a private address or a path leaving the method's tree,
is reported by the handler of its problem response. Either way the event is logged once, with the run's extras the body
carried and the request id, never a run id the caller chose, and never what was refused.
"""

import base64
import io
import json
import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, NamedTuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mthds.protocol.problem.registry import CoreCode
from pipelex.errors.error_codes import ErrorCode
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
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


class _ServerRefusal(NamedTuple):
    """A refusal of a security rule the server authors itself, and the security event it logs."""

    route: str
    body: dict[str, Any]
    error_type: str
    code: ErrorCode
    event_error_type: str
    target: str
    target_class: str | None
    refused_content: str
    """Something the request carried that the event must never hold."""


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


def _run_body() -> dict[str, Any]:
    """A run body that passes every check but the one a test breaks, naming the organization in its extras."""
    return {
        "mthds_contents": [_DESCRIBE_IMAGE_MTHDS],
        "inputs": {"photo": "https://example.com/photo.png"},
        "storage_scope": "org_abc/mt_1/run_1",
        "read_scope": "org_abc",
        "analytics_groups": {"org_id": "org_abc"},
    }


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
        # A run id the body names is the caller's claim, not a run of this runtime, before any run exists.
        assert "pipeline_run_id" not in line
        assert _LOCAL_PATH not in json.dumps(line)

    @pytest.mark.parametrize(
        "case",
        [
            pytest.param(
                _ServerRefusal(
                    route="/v1/execute",
                    body={"inputs": {"photo": {"__class__": "subprocess.Popen", "args": ["id"]}}},
                    error_type="ReservedObjectKey",
                    code=PipelexErrorCode.SECURITY_RESERVED_KEY,
                    event_error_type="ReservedObjectKey",
                    target="object_key",
                    target_class=None,
                    refused_content="__class__",
                ),
                id="reserved_object_key",
            ),
            pytest.param(
                _ServerRefusal(
                    route="/v1/start",
                    body={"callback_urls": ["http://169.254.169.254/latest/meta-data/"]},
                    error_type="InvalidCallbackUrls",
                    code=CoreCode.SECURITY_INPUT_URL_REFUSED,
                    event_error_type="CallbackUrlRefusedError",
                    target="url",
                    target_class="metadata",
                    refused_content="169.254.169.254",
                ),
                id="callback_metadata_endpoint",
            ),
            pytest.param(
                _ServerRefusal(
                    route="/v1/start",
                    body={"callback_urls": ["https://10.0.0.5/hooks/done"]},
                    error_type="InvalidCallbackUrls",
                    code=CoreCode.SECURITY_INPUT_URL_REFUSED,
                    event_error_type="CallbackUrlRefusedError",
                    target="url",
                    target_class="private",
                    refused_content="10.0.0.5",
                ),
                id="callback_private_address",
            ),
            pytest.param(
                _ServerRefusal(
                    route="/v1/start",
                    body={"callback_urls": ["http://METADATA.google.internal./computeMetadata/v1/"]},
                    error_type="InvalidCallbackUrls",
                    code=CoreCode.SECURITY_INPUT_URL_REFUSED,
                    event_error_type="CallbackUrlRefusedError",
                    target="url",
                    target_class="metadata",
                    refused_content="computeMetadata",
                ),
                id="callback_metadata_alias_spelled_otherwise",
            ),
            pytest.param(
                _ServerRefusal(
                    route="/v1/start",
                    body={"callback_urls": ["file:///etc/passwd"]},
                    error_type="InvalidCallbackUrls",
                    code=CoreCode.SECURITY_INPUT_URL_REFUSED,
                    event_error_type="CallbackUrlRefusedError",
                    target="url",
                    target_class="scheme",
                    refused_content="/etc/passwd",
                ),
                id="callback_scheme",
            ),
            pytest.param(
                _ServerRefusal(
                    route="/v1/execute",
                    body={"resources": {"../secrets/key.pem": base64.b64encode(b"x").decode("ascii")}},
                    error_type="InvalidResourcePath",
                    code=CoreCode.SECURITY_INPUT_PATH_REFUSED,
                    event_error_type="BundleResourcePathError",
                    target="path",
                    target_class=None,
                    refused_content="key.pem",
                ),
                id="resource_path_leaving_the_bundle",
            ),
            pytest.param(
                _ServerRefusal(
                    route="/v1/execute",
                    body={"mthds_contents": None, "files": {"main.mthds": _DESCRIBE_IMAGE_MTHDS, "../secrets/key.pem": "x"}},
                    error_type="InvalidMethodFiles",
                    code=CoreCode.SECURITY_INPUT_PATH_REFUSED,
                    event_error_type="MethodTreeRefusedError",
                    target="path",
                    target_class=None,
                    refused_content="key.pem",
                ),
                id="file_leaving_the_method_tree",
            ),
            pytest.param(
                _ServerRefusal(
                    route="/v1/execute",
                    body={"mthds_contents": None, "files": {"main.mthds": _DESCRIBE_IMAGE_MTHDS, "/etc/key.pem": "x"}},
                    error_type="InvalidMethodFiles",
                    code=CoreCode.SECURITY_INPUT_PATH_REFUSED,
                    event_error_type="MethodTreeRefusedError",
                    target="path",
                    target_class=None,
                    refused_content="key.pem",
                ),
                id="absolute_file_path",
            ),
        ],
    )
    def test_a_refusal_the_server_authors_logs_one_event_without_its_content(self, mocker: MockerFixture, case: _ServerRefusal) -> None:
        """The server's own refusal of a security rule keeps its response and logs the event its code calls for."""
        client = _build_client(mocker)
        request_body = {**_run_body(), "pipeline_run_id": "run-chosen-by-the-caller", **case.body}
        request_body = {key: value for key, value in request_body.items() if value is not None}

        with _security_event_lines() as lines:
            response = client.post(case.route, json=request_body, headers={REQUEST_ID_HEADER: _REQUEST_ID})

        assert response.status_code == 422, response.text
        assert response.json()["error_type"] == case.error_type
        (line,) = lines
        assert line["message"] == SECURITY_EVENT_MESSAGE
        assert line["event.name"] == SECURITY_EVENT_NAME
        assert line["error.code"] == case.code
        assert line["error.domain"] == "input"
        assert line["error.type"] == case.event_error_type
        assert line["security.target"] == case.target
        assert line.get("security.target_class") == case.target_class
        assert line["run.extras.org_id"] == "org_abc"
        assert line["request_id"] == _REQUEST_ID
        assert "pipeline_run_id" not in line
        assert case.refused_content not in json.dumps(line)

    @pytest.mark.parametrize(
        ("route", "body", "error_type"),
        [
            pytest.param("/v1/start", {"callback_urls": [""]}, "InvalidCallbackUrls", id="empty_callback_url"),
            pytest.param("/v1/start", {"callback_urls": ["https://hooks.example.com/" + "a" * 5000]}, "InvalidCallbackUrls", id="long_callback_url"),
            pytest.param("/v1/start", {"callback_urls": ["hooks.example.com/done"]}, "InvalidCallbackUrls", id="callback_url_without_scheme"),
            pytest.param("/v1/start", {"callback_urls": ["http:///done"]}, "InvalidCallbackUrls", id="callback_url_without_host"),
            pytest.param(
                "/v1/execute",
                {"mthds_contents": None, "files": {"main.mthds": _DESCRIBE_IMAGE_MTHDS, "notes//a.txt": "x"}},
                "InvalidMethodFiles",
                id="empty_segment_in_a_file_path",
            ),
            pytest.param(
                "/v1/execute",
                {"mthds_contents": None, "files": {"main.mthds": _DESCRIBE_IMAGE_MTHDS, "notes\\a.txt": "x"}},
                "InvalidMethodFiles",
                id="backslash_in_a_file_path",
            ),
        ],
    )
    def test_a_refusal_of_the_request_shape_logs_no_event(self, mocker: MockerFixture, route: str, body: dict[str, Any], error_type: str) -> None:
        """A malformed field is the caller's mistake, not an attempt to reach what a security rule forbids."""
        client = _build_client(mocker)
        request_body = {key: value for key, value in {**_run_body(), **body}.items() if value is not None}

        with _security_event_lines() as lines:
            response = client.post(route, json=request_body, headers={REQUEST_ID_HEADER: _REQUEST_ID})

        assert response.status_code == 422, response.text
        assert response.json()["error_type"] == error_type
        assert lines == []
