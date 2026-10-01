"""Smoke + hardening tests for /execute and /start (MTHDS Protocol run routes).

The actual pipeline runner is mocked: we only assert that the API layer
parses, validates, dispatches, and shapes responses correctly.
"""

import json
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipelex.base_exceptions import PipelexConfigError
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.pipeline.pipeline_response import PipelexRunResultStart, RunState
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.storage_scope import SINGLE_TENANT_USER_ID
from pytest_mock import MockerFixture

import pipelex_api.routes.pipelex.pipeline as pipeline_module
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.limits import MAX_JSON_NESTING_DEPTH
from pipelex_api.middleware import REQUEST_ID_HEADER, RequestIdMiddleware
from pipelex_api.routes.pipelex.pipeline import router as pipeline_router
from tests.unit._constants import VALID_MTHDS


def _build_client(mocker: MockerFixture, *, with_request_id_middleware: bool = False) -> tuple[TestClient, Any, Any]:
    """Wire a FastAPI app whose pipeline runner is fully mocked.

    Returns (client, execute_mock, start_mock). `with_request_id_middleware`
    wraps the ASGI app in `RequestIdMiddleware` so an inbound `X-Request-ID`
    header binds the request-scoped contextvar the route reads.
    """
    app = FastAPI()
    app.include_router(pipeline_router, prefix="/v1")
    register_exception_handlers(app)

    fake_execute_response = mocker.MagicMock()
    fake_execute_response.model_dump.return_value = {
        "pipeline_run_id": "test-run-1",
        "created_at": "2026-01-15T12:00:00Z",
        "state": "COMPLETED",
        "finished_at": "2026-01-15T12:00:01Z",
        "main_stuff_name": "main_stuff",
        "pipe_output": {"working_memory": {"root": {}, "aliases": {}}},
    }

    fake_start_response = PipelexRunResultStart(
        pipeline_run_id="test-run-1",
        created_at="2026-01-15T12:00:00Z",
        state=RunState.STARTED,
        workflow_id="wf-1",
    )

    fake_runner = mocker.MagicMock()
    fake_runner.execute = mocker.AsyncMock(return_value=fake_execute_response)
    fake_runner.start = mocker.AsyncMock(return_value=fake_start_response)
    mocker.patch("pipelex_api.routes.pipelex.pipeline.ApiRunner", return_value=fake_runner)

    asgi_app = RequestIdMiddleware(app) if with_request_id_middleware else app
    return TestClient(asgi_app), fake_runner.execute, fake_runner.start


class TestPipelineRoutes:
    def test_execute_happy_path(self, mocker: MockerFixture):
        client, execute_mock, _ = _build_client(mocker)
        response = client.post(
            "/v1/execute",
            json={"pipe_code": "echo", "mthds_contents": [VALID_MTHDS], "inputs": {"text": "hello"}},
        )
        assert response.status_code == 200
        execute_mock.assert_awaited_once()

    def test_execute_trims_tokens_usages_to_wire_records(self, mocker: MockerFixture):
        """/execute emits TokensUsageRecord wire records on pipe_output.tokens_usages — never
        the internal usage models with their job_metadata plumbing and unit_costs rate table.
        """
        client, execute_mock, _ = _build_client(mocker)
        tokens_usage = LLMTokensUsage(
            job_metadata=JobMetadata(
                run_metadata=RunMetadata(user_id="user-1", storage_scope="user-1", read_scope=None, pipeline_run_id="plr-1"), pipe_code="echo"
            ),
            inference_model_name="test-model",
            inference_model_id="test-model-id",
            nb_tokens_by_category={TokenCategory.INPUT: 10, TokenCategory.OUTPUT: 5},
            unit_costs={CostCategory.INPUT: 1.0, CostCategory.OUTPUT: 2.0},
        )
        # The route reads the usages off the response object and writes the trimmed
        # records into the dump, so seeding the object alone is what drives the assertions.
        execute_mock.return_value.pipe_output.tokens_usages = [tokens_usage]

        response = client.post(
            "/v1/execute",
            json={"pipe_code": "echo", "mthds_contents": [VALID_MTHDS], "inputs": {"text": "hello"}},
        )
        assert response.status_code == 200
        records = response.json()["pipe_output"]["tokens_usages"]
        assert len(records) == 1
        record = records[0]
        assert record["model_type"] == "llm"
        assert record["pipe_code"] == "echo"
        assert record["nb_tokens_by_category"] == {"input": 10, "output": 5}
        assert record["cost"] == 10 * (1.0 / 1_000_000) + 5 * (2.0 / 1_000_000)
        assert "job_metadata" not in record
        assert "unit_costs" not in record

    def test_execute_rejects_non_object_body(self, mocker: MockerFixture):
        client, _, _ = _build_client(mocker)
        response = client.post(
            "/v1/execute",
            content=b'"just a string"',
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "InvalidJSON"

    def test_execute_rejects_invalid_json(self, mocker: MockerFixture):
        client, _, _ = _build_client(mocker)
        response = client.post(
            "/v1/execute",
            content=b"{not json",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "InvalidJSON"

    def test_execute_rejects_recursion_error(self, mocker: MockerFixture):
        # A body nested this deep made `json.loads` raise `RecursionError` up to Python 3.13, while on
        # 3.14 it parses whenever the thread's stack is large enough. The server bounds the nesting
        # before parsing, so the answer is the same 422 InvalidJSON on every interpreter and stack,
        # never the catch-all 500 nor a later `ValidationError`.
        client, _, _ = _build_client(mocker)
        depth = 100_000
        response = client.post(
            "/v1/execute",
            content=b'{"inputs": ' + b"[" * depth + b"]" * depth + b"}",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        problem = response.json()
        assert problem["error_type"] == "InvalidJSON"
        assert problem["error_domain"] == "input"
        assert f"at most {MAX_JSON_NESTING_DEPTH} levels" in problem["detail"]
        # The opaque-500 sentinel must never appear for a caller-input failure.
        assert problem["error_type"] != "InternalServerError"

    @pytest.mark.parametrize("route", ["/v1/execute", "/v1/start"])
    def test_run_routes_bound_nesting_at_the_limit(self, mocker: MockerFixture, route: str):
        # The envelope and `inputs` are two levels, so this body nests exactly the limit and the next one level past it.
        client, execute_mock, start_mock = _build_client(mocker)

        def run_body(nesting: int) -> bytes:
            nested = b"[" * nesting + b"]" * nesting
            return b'{"pipe_code": "echo", "mthds_contents": ' + json.dumps([VALID_MTHDS]).encode() + b', "inputs": {"text": ' + nested + b"}}"

        accepted = client.post(route, content=run_body(MAX_JSON_NESTING_DEPTH - 2), headers={"content-type": "application/json"})
        assert accepted.status_code in {200, 202}, accepted.text
        assert execute_mock.await_count + start_mock.await_count == 1

        refused = client.post(route, content=run_body(MAX_JSON_NESTING_DEPTH - 1), headers={"content-type": "application/json"})
        assert refused.status_code == 422
        assert refused.json()["error_type"] == "InvalidJSON"
        assert f"at most {MAX_JSON_NESTING_DEPTH} levels" in refused.json()["detail"]
        assert execute_mock.await_count + start_mock.await_count == 1

    @pytest.mark.parametrize("route", ["/v1/execute", "/v1/start"])
    def test_run_routes_never_instantiate_a_class_the_body_names(self, mocker: MockerFixture, route: str):
        """The kajson remote-code-execution gadget: a body naming `subprocess.Popen` used to make
        the runner import it and call it with the body's arguments at decode time. The run body is
        now plain JSON, so the marker is refused with a 422 and nothing is ever called.
        """
        client, execute_mock, start_mock = _build_client(mocker)
        popen_mock = mocker.patch("subprocess.Popen")
        response = client.post(
            route,
            json={
                "pipe_code": "echo",
                "mthds_contents": [VALID_MTHDS],
                "inputs": {"text": {"__class__": "Popen", "__module__": "subprocess", "args": ["touch", "pipelex-api-rce-probe"]}},
            },
        )
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        problem = response.json()
        assert problem["error_type"] == "ReservedObjectKey"
        assert problem["error_domain"] == "input"
        popen_mock.assert_not_called()
        execute_mock.assert_not_awaited()
        start_mock.assert_not_awaited()

    @pytest.mark.parametrize(
        ("label", "body", "reserved_key"),
        [
            ("top_level_marker", {"__class__": "X", "__module__": "json", "pipe_code": "echo"}, "__class__"),
            ("module_key_alone_in_an_input", {"pipe_code": "echo", "inputs": {"doc": {"__module__": "subprocess"}}}, "__module__"),
            ("marker_inside_a_list_item", {"pipe_code": "echo", "inputs": {"docs": [{"text": "a"}, {"__class__": "Popen"}]}}, "__class__"),
            ("kajson_class_source_key", {"pipe_code": "echo", "__kajson_class_source__": "class X: pass"}, "__kajson_class_source__"),
            ("any_kajson_prefixed_key", {"pipe_code": "echo", "inputs": {"doc": {"__kajson_hint": 1}}}, "__kajson_hint"),
            ("marker_inside_an_extension_field", {"pipe_code": "echo", "analytics_groups": {"__class__": "X"}}, "__class__"),
        ],
    )
    def test_execute_refuses_reserved_object_keys(self, mocker: MockerFixture, label: str, body: dict[str, Any], reserved_key: str):
        """A key a kajson decoder reads as a class marker is refused at any depth of the body, the
        extension fields included, even though the body is parsed as plain JSON: accepted as data,
        it would come back to life when the runtime round-trips the inputs through kajson.
        """
        client, execute_mock, _ = _build_client(mocker)
        response = client.post("/v1/execute", json=body)
        assert response.status_code == 422, label
        assert response.headers["content-type"] == "application/problem+json", label
        problem = response.json()
        assert problem["error_type"] == "ReservedObjectKey", label
        assert problem["error_domain"] == "input", label
        assert f"'{reserved_key}'" in problem["detail"], label
        execute_mock.assert_not_awaited()

    def test_execute_bounds_the_reserved_key_it_echoes(self, mocker: MockerFixture):
        """Any key starting with `__kajson` is refused, so the caller picks its length. The `detail`
        names it cut to the correlation-field bound, since the detail is also logged as a field.
        """
        client, _, _ = _build_client(mocker)
        long_key = "__kajson" + "k" * 100_000
        response = client.post("/v1/execute", json={"pipe_code": "echo", "inputs": {"doc": {long_key: 1}}})
        assert response.status_code == 422
        problem = response.json()
        assert problem["error_type"] == "ReservedObjectKey"
        assert "'__kajsonkkkk" in problem["detail"]
        assert "…'" in problem["detail"]
        assert len(problem["detail"]) < 1_000

    def test_execute_accepts_marker_lookalikes_as_plain_data(self, mocker: MockerFixture):
        """Only the reserved keys themselves are refused: a value that mentions `__class__`, and a
        key that merely resembles a marker, are data and reach the runner exactly as sent.
        """
        client, execute_mock, _ = _build_client(mocker)
        inputs = {
            "text": "__class__ and __module__ are only words here",
            "doc": {"__classic__": "not a marker", "kajson": "neither is this"},
        }
        response = client.post(
            "/v1/execute",
            json={"pipe_code": "echo", "mthds_contents": [VALID_MTHDS], "inputs": inputs},
        )
        assert response.status_code == 200
        execute_mock.assert_awaited_once()
        assert execute_mock.await_args.kwargs["inputs"] == inputs

    def test_start_happy_path_returns_202(self, mocker: MockerFixture):
        client, _, start_mock = _build_client(mocker)
        response = client.post(
            "/v1/start",
            json={
                "pipe_code": "echo",
                "mthds_contents": [VALID_MTHDS],
                "inputs": {"text": "hello"},
                "callback_urls": ["https://example.com/done"],
            },
        )
        # Protocol: `POST /start` answers 202 Accepted with a StartAck.
        assert response.status_code == 202
        body = response.json()
        assert body["pipeline_run_id"] == "test-run-1"
        assert body["state"] == "STARTED"
        start_mock.assert_awaited_once()
        kwargs = start_mock.await_args.kwargs
        assert kwargs["callback_urls"] == ["https://example.com/done"]

    def test_start_forwards_client_pipeline_run_id(self, mocker: MockerFixture):
        # D11: the source-available runner ACCEPTS a client-supplied pipeline_run_id and
        # forwards it to the runner's `start` as the `pipeline_run_id` kwarg.
        client, _, start_mock = _build_client(mocker)
        response = client.post(
            "/v1/start",
            json={
                "pipe_code": "echo",
                "mthds_contents": [VALID_MTHDS],
                "inputs": {"text": "hello"},
                "pipeline_run_id": "client-chosen-run-42",
            },
        )
        assert response.status_code == 202
        start_mock.assert_awaited_once()
        assert start_mock.await_args.kwargs["pipeline_run_id"] == "client-chosen-run-42"

    def test_parse_request_binds_pipe_code_and_pipeline_run_id_to_state(self, mocker: MockerFixture):
        # End-to-end: a real POST that goes through `_parse_request` must bind
        # `pipe_code` / `pipeline_run_id` on `request.state` so that a
        # downstream failure (here: `start` raising `PipelexConfigError`)
        # is logged with both fields. The unit-level tests pin the
        # handler->getter->log path; this one pins that `_parse_request` itself
        # actually writes to `request.state` against the production route.
        # The two values reach the record as attributes of their own, so nothing about their
        # spelling matters here any more — the assertions read the `fields=` mapping the handler
        # handed the runtime, not a rendered line.
        client, _, start_mock = _build_client(mocker)
        body_pipe_code = "echo"
        body_pipeline_run_id = "run-end-to-end-0001"
        start_mock.side_effect = PipelexConfigError("simulated config fault inside the runner")
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        response = client.post(
            "/v1/start",
            json={
                "pipe_code": body_pipe_code,
                "mthds_contents": [VALID_MTHDS],
                "inputs": {"text": "hello"},
                "pipeline_run_id": body_pipeline_run_id,
            },
        )
        assert response.status_code == 500
        log_spy.error.assert_called_once()
        fields = log_spy.error.call_args.kwargs["fields"]
        assert fields["pipe_code"] == body_pipe_code
        assert fields["pipeline_run_id"] == body_pipeline_run_id

    def test_parse_request_drops_empty_correlation_fields(self, mocker: MockerFixture):
        # An empty-string `pipe_code` / `pipeline_run_id` in the body must NOT reach the record
        # as an empty attribute, which a downstream query filtering on presence would read as a
        # real value. `_coerce_correlation_field` normalizes empty strings to `None`, and
        # `_emit_api_error` drops those.
        client, _, start_mock = _build_client(mocker)
        start_mock.side_effect = PipelexConfigError("simulated config fault")
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        response = client.post(
            "/v1/start",
            json={
                "pipe_code": "",
                "mthds_contents": [VALID_MTHDS],
                "inputs": {"text": "hello"},
                "pipeline_run_id": "",
            },
        )
        assert response.status_code == 500
        log_spy.error.assert_called_once()
        fields = log_spy.error.call_args.kwargs["fields"]
        assert "pipe_code" not in fields
        assert "pipeline_run_id" not in fields

    def test_parse_request_caps_oversized_pipe_code(self, mocker: MockerFixture):
        # `RunRequest.pipe_code` carries no Pydantic max_length, so a
        # caller can in principle send a megabyte-long string. The binding
        # site caps the value that reaches the operator record, so a single failed request cannot
        # blow a log sink's per-record budget. 256 is the limit; anything longer is silently
        # truncated for the log surface (the actual `run_request.pipe_code` passed to the runner
        # is unchanged — only the `request.state` mirror is capped).
        client, _, start_mock = _build_client(mocker)
        start_mock.side_effect = PipelexConfigError("simulated config fault")
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        oversized = "x" * 5000
        response = client.post(
            "/v1/start",
            json={
                "pipe_code": oversized,
                "mthds_contents": [VALID_MTHDS],
                "inputs": {"text": "hello"},
            },
        )
        assert response.status_code == 500
        log_spy.error.assert_called_once()
        fields = log_spy.error.call_args.kwargs["fields"]
        # The capped value carries; the original oversized string does not — proof the cap fires
        # and bounds what one request costs a sink.
        assert fields["pipe_code"] == "x" * 256

    def test_parse_request_binds_pipe_code_before_extras_validation(self, mocker: MockerFixture):
        # The binding must run BEFORE `_validate_extras` so an SSRF-rejected
        # callback URL (or any other extras-validation 422) still rides the
        # caller's `pipe_code` onto the operator record. The unit-level tests
        # cannot exercise this ordering — only an end-to-end POST does.
        client, _, _ = _build_client(mocker)
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        body_pipe_code = "echo"
        response = client.post(
            "/v1/start",
            json={
                "pipe_code": body_pipe_code,
                # An AWS-metadata URL — blocked by `_is_disallowed_host`, so
                # `_validate_extras` raises 422 before `from_body` runs.
                "callback_urls": ["http://169.254.169.254/latest/meta-data/"],
            },
        )
        assert response.status_code == 422
        # An INPUT-domain 422 logs at `warning`, not `error`.
        log_spy.warning.assert_called_once()
        assert log_spy.warning.call_args.kwargs["fields"]["pipe_code"] == body_pipe_code

    def test_start_propagates_request_id_to_runner(self, mocker: MockerFixture):
        # The middleware stores the inbound `X-Request-ID` on `request.state`; the route reads it
        # back via `request_id_of(request)` and passes it as
        # `request_id=` to `ApiRunner.start`, which forwards it to
        # `pipeline_run_setup(...)` so it lands on `RunMetadata.request_id`.
        # Without this hop the worker's lines for the run would carry no `request_id`.
        client, _, start_mock = _build_client(mocker, with_request_id_middleware=True)
        inbound_request_id = "01HNJZ4XR7K3Q9D8MWAQ7FY2E5"
        response = client.post(
            "/v1/start",
            json={"pipe_code": "echo", "mthds_contents": [VALID_MTHDS], "inputs": {"text": "hello"}},
            headers={REQUEST_ID_HEADER: inbound_request_id},
        )
        assert response.status_code == 202
        assert response.headers[REQUEST_ID_HEADER] == inbound_request_id
        start_mock.assert_awaited_once()
        assert start_mock.await_args.kwargs["request_id"] == inbound_request_id

    def test_execute_propagates_request_id_to_runner(self, mocker: MockerFixture):
        # The `/execute` twin of the `/start` hop above: `ApiRunner.execute` forwards the id to the
        # runtime's `execute`, which puts it on `RunMetadata.request_id`. On a Temporal deployment
        # the whole run happens on a worker, which reads the id from that payload and nowhere else.
        client, execute_mock, _ = _build_client(mocker, with_request_id_middleware=True)
        inbound_request_id = "01HNJZ4XR7K3Q9D8MWAQ7FY2E5"
        response = client.post(
            "/v1/execute",
            json={"pipe_code": "echo", "mthds_contents": [VALID_MTHDS], "inputs": {"text": "hello"}},
            headers={REQUEST_ID_HEADER: inbound_request_id},
        )
        assert response.status_code == 200
        assert response.headers[REQUEST_ID_HEADER] == inbound_request_id
        execute_mock.assert_awaited_once()
        assert execute_mock.await_args.kwargs["request_id"] == inbound_request_id

    @pytest.mark.parametrize(
        "bad_url",
        [
            "http://169.254.169.254/latest/meta-data/",  # AWS metadata
            "http://127.0.0.1:8081/internal",  # loopback
            "http://10.0.0.5/private",  # private RFC1918
            "http://localhost/x",  # localhost name
            "file:///etc/passwd",  # disallowed scheme
            "ftp://example.com/x",  # disallowed scheme
        ],
    )
    def test_start_rejects_ssrf_callbacks(self, mocker: MockerFixture, bad_url: str):
        client, _, start_mock = _build_client(mocker)
        response = client.post(
            "/v1/start",
            json={"pipe_code": "echo", "callback_urls": [bad_url]},
        )
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "InvalidCallbackUrls"
        start_mock.assert_not_awaited()

    def test_start_rejects_too_many_callbacks(self, mocker: MockerFixture):
        client, _, start_mock = _build_client(mocker)
        response = client.post(
            "/v1/start",
            json={
                "pipe_code": "echo",
                "callback_urls": [f"https://example.com/{idx}" for idx in range(20)],
            },
        )
        # `callback_urls` exceeds `PipelineApiExtras.max_length`. The route
        # validates extras explicitly (`_validate_extras`) and re-raises the
        # resulting Pydantic `ValidationError` via `raise_validation_error`
        # with the more-specific `InvalidCallbackUrls` error_type — so the
        # response is RFC 7807 422 / `application/problem+json` but classified
        # one level finer than the generic FastAPI automatic-validation path.
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "InvalidCallbackUrls"
        start_mock.assert_not_awaited()


class TestStorageScopeReachesTheRun:
    """`storage_scope` must survive the wire -> extras -> runner hop.

    Every failure on this path is SILENT by construction, which is why the
    constructor kwarg is asserted rather than just the status code.
    The route hands the validated extras to `ApiRunner` field by field, so a
    keyword left out there is dropped with no error; the run then falls back to
    the caller's own id, writes under
    the wrong prefix, and still answers 202. On the hosted platform that is
    exactly the org-scoped storage bug — one tenant's output under another
    tenant's key — reported as success.
    """

    def test_body_storage_scope_reaches_the_runner(self, mocker: MockerFixture):
        client, _, start_mock = _build_client(mocker)
        response = client.post(
            "/v1/start",
            json={"pipe_code": "echo", "storage_scope": "org_a/mt_b/run_c"},
        )
        assert response.status_code == 202
        start_mock.assert_awaited_once()
        runner_cls = cast("Any", pipeline_module.ApiRunner)
        assert runner_cls.call_args.kwargs["storage_scope"] == "org_a/mt_b/run_c"

    def test_absent_scope_falls_back_to_the_caller_not_a_shared_literal(self, mocker: MockerFixture):
        # The fallback must be per-caller. A shared constant would pool every
        # caller of an identity-bearing deployment into one namespace — the
        # `anonymous/` collision in a new spelling.
        client, _, _ = _build_client(mocker)
        response = client.post("/v1/start", json={"pipe_code": "echo"})
        assert response.status_code == 202
        runner_cls = cast("Any", pipeline_module.ApiRunner)
        kwargs = runner_cls.call_args.kwargs
        assert kwargs["storage_scope"] == kwargs["user_id"] == SINGLE_TENANT_USER_ID

    @pytest.mark.parametrize(
        "bad_scope",
        ["../etc/passwd", "/absolute", "org//empty", "org/../escape", "", "a/b/c/d"],
    )
    def test_traversal_and_overlong_scopes_are_refused_at_the_wire(self, mocker: MockerFixture, bad_scope: str):
        # A 422 naming the field, not a 500 from deep inside the run: the value
        # becomes a storage key prefix, so a traversal in it escapes the tenant.
        client, _, start_mock = _build_client(mocker)
        response = client.post("/v1/start", json={"pipe_code": "echo", "storage_scope": bad_scope})
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        # Classified by the field that failed: this used to answer `InvalidCallbackUrls`
        # on a request that carried no callback at all.
        assert response.json()["error_type"] == "InvalidStorageScope"
        start_mock.assert_not_awaited()
