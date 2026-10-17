"""Integration tests for the global FastAPI exception handlers.

These tests register the production handlers on a throwaway FastAPI app whose
routes raise straight through — `ApiError`, `RequestValidationError`,
`PipelexError`, a bare orchestrator-SDK transport error (handled via a synthetic
plugin-contributed mapper, proving the plugin seam without importing any
orchestrator SDK), and uncaught `Exception` each end up at their respective
handler exactly the way the real app routes them. A `PipelexError` answers its
problem with the status its code declares, in the view of whoever made the
request: `as_operator` stands in for the authentication that marks a request as
the operator's, which `test_problem_views.py` drives through the real dependencies.
"""

import asyncio
import json
import re
from typing import Any, cast

import pytest
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.testclient import TestClient
from mthds.protocol.problem.registry import CoreCode
from pipelex.base_exceptions import PipelexConfigError, PipelexError, ProblemFacts
from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.config import get_config
from pipelex.errors.error_code_declaration import ErrorCodeSet
from pipelex.errors.error_codes import ErrorCode, error_code_spec
from pipelex.errors.problem import ProblemView, make_problem
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.methods.exceptions import MethodPackageSymlinkError
from pipelex.pipe_run.exceptions import AsyncExecutionNotEnabledError
from pipelex.pipeline.exceptions import PipelineManagerAlreadyExistsError
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.registrar import HttpErrorMapperFn, PluginOrigin, PluginRegistrar
from pipelex.system.exceptions import EnvVarNotFoundError
from pydantic import BaseModel, ConfigDict
from pytest_mock import MockerFixture
from starlette.types import Message, Scope
from typing_extensions import override

from pipelex_api.error_types import ErrorType
from pipelex_api.errors import raise_internal_server_error, raise_validation_error
from pipelex_api.exception_handlers import problem_response, register_exception_handlers
from pipelex_api.middleware import REQUEST_ID_HEADER, RequestIdMiddleware
from pipelex_api.problem_document import PROBLEM_JSON_MEDIA_TYPE
from pipelex_api.problem_view import mark_operator_request
from pipelex_api.routes.pipelex.pipeline import router as pipeline_router
from pipelex_api.routes.pipelex.tools import router as tools_router
from pipelex_api.security import RequestUser
from tests.unit.test_data import ProblemTestData, rate_limited_failure

# Crockford Base32, 26 chars — the ULID alphabet RequestIdMiddleware mints.
_ULID_RE = re.compile(r"\A[0-9A-HJKMNP-TV-Z]{26}\Z")

_GATEWAY_CONFIG_MESSAGE = "the gateway config is missing"
_UNEXPECTED_MESSAGE = "something nobody anticipated"
_TRANSPORT_MESSAGE = "orchestrator cluster unreachable"
# The members of the retired error report, which no problem of a `PipelexError` carries any more.
_RETIRED_REPORT_MEMBERS = ("error_type", "error_domain", "retryable", "instance", "error_category", "user_action", "provider_metadata")


def _emitted_fields(log_spy: Any, *, as_error: bool) -> dict[str, Any]:
    """The record attributes the handler shipped on its one `api_error` call.

    The handlers hand everything but the summary message to the runtime as `fields=`, so the
    assertions below read that mapping rather than parsing a rendered line: there is no rendering
    left to parse, and a sink is what decides how an attribute reaches the wire.
    """
    call = log_spy.error.call_args if as_error else log_spy.warning.call_args
    fields = call.kwargs["fields"]
    assert isinstance(fields, dict)
    return cast("dict[str, Any]", fields)


def _bare_request(path: str) -> Request:
    """A request no authentication marked, as `problem_response` receives one from a route."""
    return Request({"type": "http", "method": "GET", "path": path, "headers": [], "query_string": b""})


class _MethodSyntaxError(PipelexError):
    """A `method.syntax` failure, the method's own to fix, holding the finding its code's sentence names."""

    error_code = CoreCode.METHOD_SYNTAX

    def __init__(self, message: str, *, finding: str) -> None:
        super().__init__(message)
        self.finding = finding

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"finding": self.finding}


class _CorruptFactsError(PipelexError):
    """A `PipelexError` whose problem cannot be built — the handler-of-handlers case."""

    error_code = CoreCode.RUNTIME_UNEXPECTED

    @override
    def problem_facts(self) -> ProblemFacts:
        msg = "problem_facts is deliberately broken"
        raise RuntimeError(msg)


class _CraftedRetryError(PipelexError):
    """A provider failure knowing a retry delay, selected by case — exercises the `Retry-After` guards."""

    error_code = ErrorCodeSet(default=CoreCode.PROVIDER_RATE_LIMITED, others=(CoreCode.PROVIDER_UNAVAILABLE,))

    def __init__(self, *, retry_after: float | None) -> None:
        super().__init__("crafted retry-after scenario")
        self.retry_after = retry_after

    @override
    def problem_facts(self) -> ProblemFacts:
        return ProblemFacts(retry_after=self.retry_after)


class _SyntheticTransportError(Exception):
    """A bare orchestrator-SDK-style transport error — NOT a `PipelexError`, no `temporalio`.

    Stands in for the kind of exception an orchestrator plugin contributes a mapper for (e.g.
    `temporalio.TemporalError`), so the plugin seam — the plugin maps a bare transport exception
    to a `PipelexError`, the API renders its problem — is exercised without importing any SDK.
    """


class _SyntheticTransportFault(PipelexError):
    """The `PipelexError` the synthetic plugin's mapper stands in for an unreachable cluster."""

    error_code = CoreCode.RUNTIME_UNAVAILABLE


class _SyntheticOrchestratorError(PipelexError):
    """An orchestrator failure that IS a `PipelexError`, such as the Temporal plugin's `WorkflowExecutionError`.

    Starlette's MRO walk resolves it to `handle_pipelex_error`, never to the transport mapper
    handler registered for a bare transport exception.
    """

    error_code = CoreCode.RUN_FAILED


def _synthetic_transport_to_pipelex_error(exc: Exception) -> PipelexError:
    """The mapper an orchestrator plugin would contribute: an unreachable cluster is `runtime.unavailable`, a retryable failure."""
    fault = _SyntheticTransportFault(str(exc)).with_params(dependency="orchestrator")
    fault.__cause__ = exc
    return fault


def _synthetic_http_error_mappers() -> dict[type[Exception], HttpErrorMapperFn]:
    """Resolve a mapper the way an installed orchestrator plugin would — through the registrar SPI.

    Builds a `PluginRegistrar`, has a synthetic plugin contribute the mapper via
    `add_http_error_mapper`, and reads it back with `get_http_error_mappers` — exercising the real
    producer→consumer seam (the same one `pipelex_api.main` drives at app construction) without installing a
    plugin or importing an orchestrator SDK.
    """
    registrar = PluginRegistrar(config=get_config())
    # `group=None` is what a built-in carries: the entry-point group is how an *external* plugin
    # declares its layer, and a built-in arrives under none — it is filed by layer in-tree instead.
    registrar.begin_plugin(name="synthetic-transport-plugin", origin=PluginOrigin.BUILTIN, targets_api=PLUGIN_API_VERSION, group=None)
    registrar.add_http_error_mapper(exc_type_provider=lambda: _SyntheticTransportError, to_pipelex_error=_synthetic_transport_to_pipelex_error)
    return registrar.get_http_error_mappers()


# Route handlers are deliberately not underscore-prefixed: a private,
# decorator-only function reads as unused to the type checker.
_router = APIRouter()


@_router.get("/config-error")
async def config_error_route() -> None:
    raise PipelexConfigError(_GATEWAY_CONFIG_MESSAGE)


@_router.get("/env-error")
async def env_error_route() -> None:
    msg = "Environment variable 'COMPLETION_CALLBACK_SECRET' is required but not set"
    raise EnvVarNotFoundError(msg)


@_router.get("/input-error")
async def input_error_route() -> None:
    msg = "your .mthds file has a syntax error on line 4"
    raise _MethodSyntaxError(msg, finding="TOML syntax error at line 4")


@_router.get("/llm-error")
async def llm_error_route() -> None:
    raise rate_limited_failure()


@_router.get("/corrupt-error")
async def corrupt_error_route() -> None:
    msg = "its problem builder is broken"
    raise _CorruptFactsError(msg)


@_router.get("/orchestrator-pipelex-error")
async def orchestrator_pipelex_error_route() -> None:
    msg = "the workflow failed"
    raise _SyntheticOrchestratorError(msg).with_params(pipeline_run_id="run-7", run_status="FAILED")


@_router.get("/async-execution-not-enabled")
async def async_execution_not_enabled_route() -> None:
    # Pipelex raises this when an async dispatch site is reached on a deployment without an async
    # execution backend enabled; its code, `runtime.unsupported`, declares 501.
    msg = "Asynchronous pipeline execution is not enabled on this deployment."
    raise AsyncExecutionNotEnabledError(msg)


@_router.get("/pipeline-run-id-conflict")
async def pipeline_run_id_conflict_route() -> None:
    # Pipelex raises this from ``add_new_pipeline`` when a submission reuses a ``pipeline_run_id``
    # that is still registered; its code, `pipelex.run.already_exists`, declares 409.
    msg = "Pipeline some-run-id already exists"
    raise PipelineManagerAlreadyExistsError(msg)


@_router.get("/method-package-symlink")
async def method_package_symlink_route() -> None:
    # Pipelex raises this from ``ensure_package_within_bounds`` when a package fetched by
    # ``method_ref`` carries a symlink; its code, `method.package_invalid`, declares 422.
    msg = "Method package 'github.com/acme/linked' contains a symlink ('vendored') — fetched packages must not contain symlinks."
    raise MethodPackageSymlinkError(msg)


@_router.get("/synthetic-transport-error")
async def synthetic_transport_error_route() -> None:
    raise _SyntheticTransportError(_TRANSPORT_MESSAGE)


@_router.get("/unexpected-error")
async def unexpected_error_route() -> None:
    raise RuntimeError(_UNEXPECTED_MESSAGE)


@_router.get("/crafted-retry/{case}")
async def crafted_retry_route(case: str) -> None:
    code, retry_after, _, _, _ = ProblemTestData.RETRY_CASES[case]
    raise _CraftedRetryError(retry_after=retry_after).with_error_code(code)


@_router.get("/api-input-error")
async def api_input_error_route() -> None:
    # An API-authored 422 — the INPUT-domain branch of `handle_api_error`.
    raise_validation_error("a caller-side mistake")


@_router.get("/crafted-detail")
async def crafted_detail_route(detail: str) -> None:
    # An API-authored 422 whose `detail` is exactly what the caller sent — the real shape of the
    # `raise_validation_error(str(exc))` sites, where the message is built from caller input.
    raise_validation_error(detail)


@_router.get("/api-config-error")
async def api_config_error_route() -> None:
    # An API-authored 500 — the CONFIG-domain branch of `handle_api_error`
    # (the `version.py` `PackageNotFoundError → raise_internal_server_error`
    # path goes through this same code).
    raise_internal_server_error("the configuration is broken", error_type=ErrorType.SERVER_MISCONFIGURED)


class _RequestValidationBody(BaseModel):
    """Trivial schema for `test_request_validation_error_emits_structured_warning_log`.

    A POST that is both missing `field` and carries an unknown key triggers
    FastAPI's automatic `RequestValidationError`, which is what we want to
    log-test. `extra="forbid"` matches the strictest production schemas
    (`UploadRequest`, `ResolveStorageUrlRequest`) and ensures both the
    missing-field and the extra-field branches of the validation surface
    fire on a single request — Pydantic's default `extra="ignore"` would
    silently drop the unknown key.
    """

    model_config = ConfigDict(extra="forbid")

    field: str


@_router.post("/needs-body")
async def needs_body_route(_body: _RequestValidationBody) -> None:
    return None


# A canonical user_id for the authenticated test routes — a realistic
# path-safe id (`pipelex_api.security.is_safe_user_id`), so the routes mirror real
# auth state rather than a placeholder string.
_TEST_USER_ID = "00000000-0000-0000-0000-000000000001"


def _bind_test_user(request: Request) -> None:
    """Set `request.state.user` the same shape `pipelex_api.security._set_request_user` would.

    The throwaway app does not run the real auth dependency — these routes stand
    in for "auth succeeded" so the error-log enrichment can be exercised
    without dragging in JWT validation.
    """
    request.state.user = RequestUser(user_id=_TEST_USER_ID)


# Canonical body-derived identifiers for the pipeline-state routes — bound on
# `request.state` the same way `pipelex_api.routes.pipelex.pipeline._parse_request`
# binds them in production.
_TEST_PIPE_CODE = "echo"
_TEST_RUN_ID = "run-00000000-0000-0000-0000-000000000099"


def _bind_test_run_state(request: Request) -> None:
    """Set `request.state.pipe_code` / `pipeline_run_id` the same shape `_parse_request` would.

    Stand-in for "the body was parsed and the two identifiers were bound" so
    the error-log enrichment can be exercised against the handler functions
    without driving a real `/execute` body through `_parse_request`.
    """
    request.state.pipe_code = _TEST_PIPE_CODE
    request.state.pipeline_run_id = _TEST_RUN_ID


@_router.get("/authenticated-config-error")
async def authenticated_config_error_route(request: Request) -> None:
    _bind_test_user(request)
    raise PipelexConfigError(_GATEWAY_CONFIG_MESSAGE)


@_router.get("/authenticated-api-input-error")
async def authenticated_api_input_error_route(request: Request) -> None:
    _bind_test_user(request)
    raise_validation_error("a caller-side mistake")


@_router.get("/authenticated-unexpected-error")
async def authenticated_unexpected_error_route(request: Request) -> None:
    _bind_test_user(request)
    raise RuntimeError(_UNEXPECTED_MESSAGE)


@_router.get("/pipeline-state-pipelex-error")
async def run_state_pipelex_error_route(request: Request) -> None:
    # Stand-in for the production flow: a body went through `_parse_request`
    # (state bound), then pipelex raised a `PipelexError` further down the
    # stack. Exercises `_log_problem`.
    _bind_test_run_state(request)
    raise PipelexConfigError(_GATEWAY_CONFIG_MESSAGE)


@_router.get("/pipeline-state-api-input-error")
async def run_state_api_input_error_route(request: Request) -> None:
    # An API-authored 4xx raised after `_parse_request` bound state — exercises
    # `_log_api_authored_error`.
    _bind_test_run_state(request)
    raise_validation_error("a caller-side mistake")


@_router.get("/pipeline-state-unexpected-error")
async def run_state_unexpected_error_route(request: Request) -> None:
    # An unclassified exception escaping after `_parse_request` bound state —
    # exercises the catch-all `handle_unexpected_error` log path. The most
    # operationally expensive case: by definition the failure was not
    # classifiable upstream, so carrying the pipe-state identifiers is what
    # gives the operator a starting point for debugging.
    _bind_test_run_state(request)
    raise RuntimeError(_UNEXPECTED_MESSAGE)


def _gateway_failure() -> LLMCompletionError:
    """An inference failure whose SDK metadata names the provider family, `gateway`, and no backend."""
    return LLMCompletionError(
        "the gateway is unavailable",
        error_category=InferenceErrorCategory.TRANSIENT,
        provider_metadata=ProviderErrorMetadata(provider=ProviderName.GATEWAY, sdk_exception_type="APIStatusError", status_code=503),
    )


@_router.get("/inference-failure-attributed")
async def inference_failure_attributed_route() -> None:
    # A failure the worker's chokepoint attributed: the error names the backend that served the model.
    gateway_failure = _gateway_failure()
    gateway_failure.fill_model_and_provider("claude-5.5-sonnet", backend_name="pipelex_gateway")
    raise gateway_failure


@_router.get("/inference-failure-unattributed")
async def inference_failure_unattributed_route() -> None:
    # A failure no worker attributed: only the SDK's metadata names who answered.
    raise _gateway_failure()


def _build_client(
    *,
    raise_server_exceptions: bool = True,
    as_operator: bool = False,
    http_error_mappers: dict[type[Exception], HttpErrorMapperFn] | None = None,
) -> TestClient:
    """Wire a throwaway app with the production handlers and request-id middleware.

    `raise_server_exceptions` must be `False` for tests that hit the catch-all
    handler: Starlette's `ServerErrorMiddleware` always re-raises after running
    its handler, so the `TestClient` would otherwise surface the exception
    instead of the response. `as_operator` marks every request as the operator's,
    as `verify_api_key` and a trusted proxy's forwarded identity do, so its
    failures answer the operator view; unmarked, they answer the caller view.
    `http_error_mappers` are the orchestrator-plugin mappers to register a
    transport handler per `exc_type` for — defaults to none (the agnostic base).
    """
    app = FastAPI()
    register_exception_handlers(app, http_error_mappers=http_error_mappers)
    app.include_router(_router, dependencies=[Depends(mark_operator_request)] if as_operator else [])
    return TestClient(RequestIdMiddleware(app), raise_server_exceptions=raise_server_exceptions)


class TestExceptionHandlers:
    def test_pipelex_error_produces_problem_json(self):
        response = _build_client(as_operator=True).get("/config-error")
        assert response.status_code == 500
        assert response.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
        body = response.json()
        config_invalid = error_code_spec(PipelexErrorCode.CONFIG_INVALID)
        assert body["code"] == PipelexErrorCode.CONFIG_INVALID
        assert body["type"] == config_invalid.type_uri
        assert body["title"] == config_invalid.title
        assert body["status"] == 500
        # The detail is the code's own sentence; the error's message is what the operator reads in `diagnostics`.
        assert body["detail"] == config_invalid.detail
        assert body["domain"] == "operator"
        assert body["retry"] == "no"
        assert body["next_step"]["kind"] == "fix_configuration"
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]
        assert body["diagnostics"]["error_class"] == "PipelexConfigError"
        assert body["diagnostics"]["message"] == _GATEWAY_CONFIG_MESSAGE
        # The members of the retired error report are gone from a problem of a `PipelexError`.
        for retired_member in _RETIRED_REPORT_MEMBERS:
            assert retired_member not in body, retired_member

    def test_env_var_not_found_error_is_config_500(self):
        # A missing required env var is an operator-fixable misconfiguration: `pipelex.config.variable_missing`, a 500
        # in the operator domain, whose variable only the operator reads.
        operator_body = _build_client(as_operator=True).get("/env-error").json()
        assert operator_body["status"] == 500
        assert operator_body["code"] == PipelexErrorCode.CONFIG_VARIABLE_MISSING
        assert operator_body["domain"] == "operator"
        assert operator_body["diagnostics"]["error_class"] == "EnvVarNotFoundError"
        assert "COMPLETION_CALLBACK_SECRET" in operator_body["diagnostics"]["message"]

        caller_response = _build_client().get("/env-error")
        assert caller_response.status_code == 500
        assert caller_response.json()["code"] == PipelexErrorCode.CONFIG_VARIABLE_MISSING
        assert "COMPLETION_CALLBACK_SECRET" not in caller_response.text

    def test_the_caller_view_withholds_what_only_the_operator_reads(self):
        # An operator's fault reaches the caller as its code, its sentence and a step it can take, and never the
        # error's message; a fault of the caller's own method reaches it with the parameters its sentence names.
        client = _build_client()

        config_response = client.get("/config-error")
        assert config_response.status_code == 500
        config_body = config_response.json()
        assert config_body["code"] == PipelexErrorCode.CONFIG_INVALID
        assert config_body["next_step"]["kind"] == "report"
        assert "diagnostics" not in config_body
        assert _GATEWAY_CONFIG_MESSAGE not in config_response.text

        input_response = client.get("/input-error")
        assert input_response.status_code == 422
        input_body = input_response.json()
        assert input_body["code"] == CoreCode.METHOD_SYNTAX
        assert input_body["domain"] == "method"
        assert input_body["params"] == {"finding": "TOML syntax error at line 4"}
        assert input_body["detail"] == "The method does not parse (TOML syntax error at line 4)."
        assert "diagnostics" not in input_body

    def test_provider_rate_limit_emits_retry_after(self):
        response = _build_client(as_operator=True).get("/llm-error")
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "12"
        body = response.json()
        assert body["code"] == CoreCode.PROVIDER_RATE_LIMITED
        assert body["retry"] == "yes"
        assert body["retry_after"] == ProblemTestData.RATE_LIMIT_RETRY_AFTER_SECONDS
        assert body["next_step"]["kind"] == "wait"
        assert body["params"] == {"model": ProblemTestData.RATE_LIMIT_MODEL, "provider": ProblemTestData.RATE_LIMIT_BACKEND}
        assert body["detail"] == ProblemTestData.RATE_LIMIT_DETAIL
        # What the provider said rides the operator's diagnostics, never the caller's view.
        assert body["diagnostics"]["error_class"] == "LLMCompletionError"
        assert body["diagnostics"]["message"] == ProblemTestData.RATE_LIMIT_MESSAGE
        assert body["diagnostics"]["model"] == ProblemTestData.RATE_LIMIT_MODEL
        assert body["diagnostics"]["provider"] == {
            "name": ProblemTestData.RATE_LIMIT_BACKEND,
            "status": 429,
            "request_id": ProblemTestData.RATE_LIMIT_PROVIDER_REQUEST_ID,
        }

    @pytest.mark.parametrize("case", list(ProblemTestData.RETRY_CASES))
    def test_retry_after_header_is_guarded(self, case: str):
        """`Retry-After` rides a 429 alone, and only when the delay is a finite, non-negative number, rounded up."""
        _, _, expected_status, expected_header, expected_retry_after = ProblemTestData.RETRY_CASES[case]

        response = _build_client().get(f"/crafted-retry/{case}")

        assert response.status_code == expected_status
        assert response.json()["status"] == expected_status
        assert response.headers.get("Retry-After") == expected_header
        assert response.json().get("retry_after") == expected_retry_after

    @pytest.mark.parametrize(("code", "expected_status"), ProblemTestData.CODE_STATUSES)
    def test_the_status_is_the_one_the_code_declares(self, mocker: MockerFixture, code: ErrorCode, expected_status: int):
        """The response's status, the body's `status` member and the record's are the registry's, one value for all three."""
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")

        response = problem_response(make_problem(code=code, view=ProblemView.OPERATOR), error=None, request=_bare_request("/coded"))

        assert error_code_spec(code).status == expected_status
        assert response.status_code == expected_status
        body = json.loads(bytes(response.body))
        assert body["status"] == expected_status
        assert body["code"] == code
        fields = _emitted_fields(log_spy, as_error=expected_status >= 500)
        assert fields["http.response.status_code"] == expected_status
        assert fields["error.code"] == code

    def test_a_code_the_registry_does_not_know_falls_back_to_500(self, mocker: MockerFixture):
        """A code no registry entry parses, which only a client's own failure has, still answers a status: 500."""
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        problem = make_problem(code=CoreCode.RUNTIME_UNEXPECTED, view=ProblemView.OPERATOR).model_copy(update={"code": "x.unknown"})

        response = problem_response(problem, error=None, request=_bare_request("/unknown-code"))

        assert response.status_code == 500
        body = json.loads(bytes(response.body))
        assert body["status"] == 500
        assert body["code"] == "x.unknown"
        assert "retry-after" not in response.headers
        fields = _emitted_fields(log_spy, as_error=True)
        assert fields["http.response.status_code"] == 500

    @pytest.mark.parametrize("as_operator", [True, False], ids=["operator", "caller"])
    def test_unexpected_error_is_runtime_unexpected(self, as_operator: bool):
        """An unclassified failure answers `runtime.unexpected`: its own sentences to the caller, its class and message to the operator."""
        response = _build_client(raise_server_exceptions=False, as_operator=as_operator).get("/unexpected-error")
        assert response.status_code == 500
        assert response.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
        body = response.json()
        runtime_unexpected = error_code_spec(CoreCode.RUNTIME_UNEXPECTED)
        assert body["code"] == CoreCode.RUNTIME_UNEXPECTED
        assert body["type"] == runtime_unexpected.type_uri
        assert body["detail"] == runtime_unexpected.detail
        assert body["domain"] == "runtime"
        assert body["retry"] == "no"
        assert body["next_step"]["kind"] == "report"
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]
        assert "error_type" not in body
        if as_operator:
            assert body["diagnostics"]["error_class"] == "PipelexUnexpectedError"
            assert body["diagnostics"]["message"] == f"RuntimeError: {_UNEXPECTED_MESSAGE}"
            assert body["diagnostics"]["causes"] == [{"error_class": "RuntimeError"}]
        else:
            assert "diagnostics" not in body
            assert "RuntimeError" not in response.text
            assert _UNEXPECTED_MESSAGE not in response.text

    @pytest.mark.parametrize("as_operator", [True, False], ids=["operator", "caller"])
    def test_unexpected_error_never_leaks_a_traceback(self, as_operator: bool):
        # The operator reads the message, never the stack: a traceback stays an operator-log artifact in both views.
        response = _build_client(raise_server_exceptions=False, as_operator=as_operator).get("/unexpected-error")
        assert "Traceback" not in response.text
        assert "unexpected_error_route" not in response.text

    def test_orchestrator_error_dispatch(self):
        # The plugin seam: a synthetic plugin contributes a transport mapper through the registrar SPI, the app registers
        # one handler per mapped exc_type, and a bare transport error answers the problem of the `PipelexError` the
        # mapper returned — all without importing any orchestrator SDK.
        client = _build_client(as_operator=True, http_error_mappers=_synthetic_http_error_mappers())

        # An orchestrator failure that IS a PipelexError is routed to the PipelexError handler, NOT the transport
        # mapper handler: `run.failed`, which declares 409.
        pipelex_response = client.get("/orchestrator-pipelex-error")
        assert pipelex_response.status_code == 409
        pipelex_body = pipelex_response.json()
        assert pipelex_body["code"] == CoreCode.RUN_FAILED
        assert pipelex_body["detail"] == "The run 'run-7' ended as 'FAILED', without success."
        assert pipelex_body["diagnostics"]["error_class"] == "_SyntheticOrchestratorError"

        # A bare transport error is routed to the plugin's mapper-backed handler: `runtime.unavailable`, a retryable 503,
        # whose operator-only parameter rides the diagnostics.
        transport_response = client.get("/synthetic-transport-error")
        assert transport_response.status_code == 503
        transport_body = transport_response.json()
        assert transport_body["code"] == CoreCode.RUNTIME_UNAVAILABLE
        assert transport_body["retry"] == "yes"
        assert transport_body["diagnostics"]["error_class"] == "_SyntheticTransportFault"
        assert transport_body["diagnostics"]["message"] == _TRANSPORT_MESSAGE
        assert transport_body["diagnostics"]["params"] == {"dependency": "orchestrator"}
        assert "params" not in transport_body

    def test_mapped_transport_error_answers_the_caller_without_its_diagnostics(self):
        response = _build_client(http_error_mappers=_synthetic_http_error_mappers()).get("/synthetic-transport-error")
        assert response.status_code == 503
        body = response.json()
        assert body["code"] == CoreCode.RUNTIME_UNAVAILABLE
        assert "diagnostics" not in body
        assert _TRANSPORT_MESSAGE not in response.text
        assert "orchestrator" not in json.dumps(body.get("params", {}))

    def test_unmapped_transport_error_falls_back_to_catch_all_500(self):
        # Without the orchestrator plugin's mapper (the agnostic base), the same bare transport error has no dedicated
        # handler and collapses to the catch-all `runtime.unexpected` — whose diagnostics still tell the operator which
        # transport class failed and why.
        response = _build_client(raise_server_exceptions=False, as_operator=True).get("/synthetic-transport-error")
        assert response.status_code == 500
        body = response.json()
        assert body["code"] == CoreCode.RUNTIME_UNEXPECTED
        assert body["diagnostics"]["message"] == f"_SyntheticTransportError: {_TRANSPORT_MESSAGE}"

    def test_handler_of_handlers_catches_a_corrupt_problem(self):
        # When building the problem itself raises, the failure escapes the PipelexError handler; ServerErrorMiddleware
        # funnels it into the catch-all — a real 500 body, never a bodyless default. The class the diagnostics name is
        # the one raised *by the broken builder*, not the original error.
        response = _build_client(raise_server_exceptions=False, as_operator=True).get("/corrupt-error")
        assert response.status_code == 500
        body = response.json()
        assert body["code"] == CoreCode.RUNTIME_UNEXPECTED
        assert body["diagnostics"]["message"] == "RuntimeError: problem_facts is deliberately broken"

    @pytest.mark.parametrize(
        ("method", "path", "json_body", "expected_status"),
        [
            ("GET", "/config-error", None, 500),
            ("GET", "/env-error", None, 500),
            ("GET", "/input-error", None, 422),
            ("GET", "/llm-error", None, 429),
            ("GET", "/orchestrator-pipelex-error", None, 409),
            ("GET", "/synthetic-transport-error", None, 500),
            ("GET", "/corrupt-error", None, 500),
            ("GET", "/unexpected-error", None, 500),
            # Cover the API-authored paths (`handle_api_error`) and FastAPI's
            # automatic-validation path (`handle_request_validation_error`):
            # the request-id propagation is the same structural property, but
            # the three branches build the response document differently and
            # are worth sweeping.
            ("GET", "/api-input-error", None, 422),
            ("GET", "/api-config-error", None, 500),
            ("POST", "/needs-body", {"wrong": 1}, 422),
        ],
    )
    def test_request_id_present_on_every_error_response(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None,
        expected_status: int,
    ):
        response = _build_client(raise_server_exceptions=False).request(method, path, json=json_body)
        assert response.status_code == expected_status
        request_id = response.headers[REQUEST_ID_HEADER]
        assert _ULID_RE.match(request_id) is not None
        assert response.json()["request_id"] == request_id

    def test_inbound_request_id_is_echoed(self):
        response = _build_client().get("/config-error", headers={REQUEST_ID_HEADER: "inbound-correlation-007"})
        assert response.headers[REQUEST_ID_HEADER] == "inbound-correlation-007"
        assert response.json()["request_id"] == "inbound-correlation-007"

    def test_pipelex_error_record_names_the_code_and_the_class(self, mocker: MockerFixture):
        # The record is built from the operator view whichever view the response carries: the caller's body names no
        # class, the record does, beside the code a sink groups failures by.
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        response = _build_client().get("/config-error")
        assert response.status_code == 500
        assert "diagnostics" not in response.json()
        log_spy.error.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=True)
        assert fields["error.code"] == PipelexErrorCode.CONFIG_INVALID
        assert fields["error.type"] == "PipelexConfigError"
        assert fields["error_domain"] == "config"
        assert fields["retryable"] is False
        assert fields["http.response.status_code"] == 500
        assert fields["url.path"] == "/config-error"
        # A domain error's record carries no `detail`: the cause is the diagnostics', the body's detail is only its code's sentence.
        assert "detail" not in fields
        assert log_spy.error.call_args.kwargs["include_exception"] is True

    def test_provider_failure_record_carries_the_providers_answer(self, mocker: MockerFixture):
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        response = _build_client().get("/llm-error")
        assert response.status_code == 429
        # A provider's 429 passed through is no fault of this server: a warning, without a traceback.
        log_spy.warning.assert_called_once()
        log_spy.error.assert_not_called()
        fields = _emitted_fields(log_spy, as_error=False)
        assert fields["error.code"] == CoreCode.PROVIDER_RATE_LIMITED
        assert fields["error.type"] == "LLMCompletionError"
        assert fields["error_category"] == InferenceErrorCategory.TRANSIENT
        assert fields["retryable"] is True
        assert fields["backend_name"] == ProblemTestData.RATE_LIMIT_BACKEND
        assert fields["model_handle"] == ProblemTestData.RATE_LIMIT_MODEL
        assert fields["provider_status_code"] == 429
        assert fields["provider_request_id"] == ProblemTestData.RATE_LIMIT_PROVIDER_REQUEST_ID

    def test_unexpected_error_record_names_the_class_that_escaped(self, mocker: MockerFixture):
        # The catch-all's record is the operator's only handle on a failure nothing classified, so it names the class
        # that escaped, which a sink groups unexpected failures by, beside the code they all share.
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        response = _build_client(raise_server_exceptions=False).get("/unexpected-error")
        assert response.status_code == 500
        log_spy.error.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=True)
        assert fields["error.code"] == CoreCode.RUNTIME_UNEXPECTED
        assert fields["error.type"] == "RuntimeError"
        assert log_spy.error.call_args.kwargs["include_exception"] is True

    def test_api_authored_500_emits_structured_error_record(self, mocker: MockerFixture):
        # Without `handle_api_error` logging, an `ApiError`-shaped 500 produces
        # zero operator output (`/version`'s `PackageNotFoundError →
        # raise_internal_server_error` is the canonical silent case). Assert
        # the handler emits one `api_error` record at `error` level whose fields
        # mirror the response — the same set `_log_problem` ships for a
        # pipelex-derived 500, so a downstream sink queries them uniformly.
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        response = _build_client().get("/api-config-error")
        assert response.status_code == 500
        log_spy.error.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=True)
        assert fields["http.response.status_code"] == 500
        assert fields["error.type"] == "ServerMisconfigured"
        assert fields["error_domain"] == "config"
        assert fields["retryable"] is False
        assert fields["url.path"] == "/api-config-error"
        # The operator-facing cause rides a field of its own and never reaches the message, which
        # is what stops a crafted value from shaping the rendered line at all.
        assert fields["detail"] == "the configuration is broken"
        assert log_spy.error.call_args.kwargs["include_exception"] is True
        log_spy.warning.assert_not_called()

    def test_api_authored_4xx_emits_structured_warning_record(self, mocker: MockerFixture):
        # Mirror at the warning level: an INPUT-domain `ApiError` is a caller
        # mistake, not an operator fault, so it logs at `warning` without a
        # traceback — same disposition rule `_log_problem` uses.
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        response = _build_client().get("/api-input-error")
        assert response.status_code == 422
        log_spy.warning.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=False)
        assert fields["http.response.status_code"] == 422
        assert fields["error.type"] == "ValidationError"
        assert fields["error_domain"] == "input"
        assert fields["retryable"] is False
        assert fields["detail"] == "a caller-side mistake"
        log_spy.error.assert_not_called()

    @pytest.mark.parametrize("path", ["/v1/lint", "/v1/execute"], ids=["typed-body-route", "raw-body-run-route"])
    def test_client_disconnect_is_a_400_logged_as_a_warning(self, mocker: MockerFixture, path: str):
        # A client that leaves mid-upload makes the body read raise `ClientDisconnect`, from a typed route's
        # nesting check or from a run route's own read. It is the caller's failure: a 400 at warning, never a
        # 500 server fault with a traceback.
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(tools_router, prefix="/v1")
        app.include_router(pipeline_router, prefix="/v1")
        sent: list[Message] = []
        reads = 0

        async def receive() -> Message:
            # The first read gets the start of the body; every later one finds the client gone.
            nonlocal reads
            reads += 1
            if reads == 1:
                return {"type": "http.request", "body": b'{"content": "dom', "more_body": True}
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            sent.append(message)

        scope: Scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "root_path": "",
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
        asyncio.run(app(scope, receive, send))

        start = next(message for message in sent if message["type"] == "http.response.start")
        assert start["status"] == 400
        body = json.loads(b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body"))
        assert body["error_type"] == "BadRequest"
        assert body["error_domain"] == "input"
        log_spy.warning.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=False)
        assert fields["http.response.status_code"] == 400
        assert fields["error.type"] == "BadRequest"
        log_spy.error.assert_not_called()

    def test_the_message_is_fixed_and_the_failure_rides_the_fields(self, mocker: MockerFixture):
        # The message is the same sentence on every error line, at either level, so it is the key a
        # query or an alert selects the error stream by; the status and the error type, which used
        # to be spliced into it, ride fields under their OpenTelemetry keys.
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        assert _build_client().get("/api-config-error").status_code == 500
        assert _build_client().get("/api-input-error").status_code == 422
        assert log_spy.error.call_args.args[0] == "A request ended in an error response"
        assert log_spy.warning.call_args.args[0] == "A request ended in an error response"
        fields = _emitted_fields(log_spy, as_error=True)
        assert fields["http.response.status_code"] == 500
        assert fields["error.type"] == "ServerMisconfigured"
        assert "event" not in fields

    @pytest.mark.parametrize(
        ("path", "expected_backend_name"),
        [
            ("/inference-failure-attributed", "pipelex_gateway"),
            ("/inference-failure-unattributed", None),
        ],
    )
    def test_backend_name_is_only_ever_the_backend_the_error_names(self, mocker: MockerFixture, path: str, expected_backend_name: str | None):
        """The provider the SDK's metadata names, `gateway`, is no backend's name: it is never written under `backend_name`, nor under `sdk`."""
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        response = _build_client().get(path)
        # A provider answering 503 is `provider.unavailable`, whose registry entry declares 502.
        assert response.status_code == 502
        assert response.json()["code"] == CoreCode.PROVIDER_UNAVAILABLE
        fields = _emitted_fields(log_spy, as_error=True)
        assert fields.get("backend_name") == expected_backend_name
        assert "sdk" not in fields
        assert ProviderName.GATEWAY not in fields.values()
        assert fields["provider_status_code"] == 503

    def test_user_id_rides_authenticated_pipelex_error_record(self, mocker: MockerFixture):
        # The global handler reads `request.state.user` so the operator can tie a `PipelexError` to the caller
        # through the record alone — no correlating across records on `request_id` required.
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        response = _build_client().get("/authenticated-config-error")
        assert response.status_code == 500
        log_spy.error.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=True)
        assert fields["user.id"] == _TEST_USER_ID
        assert fields["error.type"] == "PipelexConfigError"
        assert fields["error.code"] == PipelexErrorCode.CONFIG_INVALID

    def test_user_id_rides_authenticated_api_authored_record(self, mocker: MockerFixture):
        # `handle_api_error` covers the API-authored 4xx surface (storage's
        # `raise_bad_request`, `raise_forbidden`, `raise_payload_too_large`;
        # uploader's same set). It must ride the same `user.id` correlation
        # `_log_problem` does so the contract is uniform — a caller
        # mistake and a backend failure both name the caller.
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        response = _build_client().get("/authenticated-api-input-error")
        assert response.status_code == 422
        log_spy.warning.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=False)
        assert fields["user.id"] == _TEST_USER_ID
        assert fields["error.type"] == "ValidationError"

    def test_user_id_rides_authenticated_unexpected_error_record(self, mocker: MockerFixture):
        # The catch-all 500 (`handle_unexpected_error`) is the one place a
        # missing `user.id` is most expensive — by definition the failure
        # was not classifiable upstream — so the same enrichment fires here.
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        response = _build_client(raise_server_exceptions=False).get("/authenticated-unexpected-error")
        assert response.status_code == 500
        log_spy.error.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=True)
        assert fields["user.id"] == _TEST_USER_ID
        assert fields["error.code"] == CoreCode.RUNTIME_UNEXPECTED

    def test_user_id_absent_from_unauthenticated_error_record(self, mocker: MockerFixture):
        # Pre-auth paths, and a deployment with no user model, have no `request.state.user`;
        # `_user_id_of` returns `None` and `_emit_api_error` drops `None`-valued fields, so the
        # record carries no `user.id` attribute at all — never a null, which a query filtering on
        # presence would read as an answer.
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        response = _build_client().get("/config-error")
        assert response.status_code == 500
        log_spy.error.assert_called_once()
        assert "user.id" not in _emitted_fields(log_spy, as_error=True)

    def test_run_state_rides_pipelex_error_record(self, mocker: MockerFixture):
        # `_parse_request` binds `pipe_code` / `pipeline_run_id` on `request.state` so a downstream pipelex failure is
        # tied to the specific pipe and run id without each backend frame having to forward them.
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        response = _build_client().get("/pipeline-state-pipelex-error")
        assert response.status_code == 500
        log_spy.error.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=True)
        assert fields["pipe_code"] == _TEST_PIPE_CODE
        assert fields["pipeline_run_id"] == _TEST_RUN_ID
        assert fields["error.type"] == "PipelexConfigError"
        # The bound run id rides the problem too, so a caller can name the run it asks about.
        assert response.json()["pipeline_run_id"] == _TEST_RUN_ID

    def test_run_state_rides_api_authored_record(self, mocker: MockerFixture):
        # API-authored 4xx surface: `raise_validation_error` raised from a
        # route that has already bound pipe state must ship the same fields,
        # so the operator record is uniform across the validation and the
        # pipelex-domain failure surfaces.
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        response = _build_client().get("/pipeline-state-api-input-error")
        assert response.status_code == 422
        log_spy.warning.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=False)
        assert fields["pipe_code"] == _TEST_PIPE_CODE
        assert fields["pipeline_run_id"] == _TEST_RUN_ID
        assert fields["error.type"] == "ValidationError"

    def test_run_state_rides_unexpected_error_record(self, mocker: MockerFixture):
        # The catch-all 500 is the most operationally expensive case for a
        # missing pipe-state field — by definition the failure was not
        # classifiable upstream, so the identifiers on the record are the
        # operator's only starting point for which pipe and which run were
        # in flight.
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        response = _build_client(raise_server_exceptions=False).get("/pipeline-state-unexpected-error")
        assert response.status_code == 500
        log_spy.error.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=True)
        assert fields["pipe_code"] == _TEST_PIPE_CODE
        assert fields["pipeline_run_id"] == _TEST_RUN_ID
        assert fields["error.code"] == CoreCode.RUNTIME_UNEXPECTED

    def test_run_state_absent_when_parse_request_did_not_bind(self, mocker: MockerFixture):
        # A route that didn't go through `_parse_request` (here: `/config-error`,
        # a GET that never touches the body) has no `pipe_code` /
        # `pipeline_run_id` on `request.state`. The getters return `None` and
        # `_emit_api_error` drops those, so the record carries neither attribute.
        # Same defensive posture as `test_user_id_absent_from_unauthenticated_error_record`.
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        response = _build_client().get("/config-error")
        assert response.status_code == 500
        log_spy.error.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=True)
        assert "pipe_code" not in fields
        assert "pipeline_run_id" not in fields
        assert "pipeline_run_id" not in response.json()

    def test_request_validation_error_emits_structured_warning_record(self, mocker: MockerFixture):
        # FastAPI's automatic-validation 422 goes through
        # `handle_request_validation_error`, not `handle_api_error`, but emits
        # the same `api_error` record so the surface is uniform — whichever code
        # path rejects a caller-input failure, the operator record is identical.
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        # `{"wrong": 1}` triggers FastAPI's automatic validation failure on
        # `_RequestValidationBody`: `field` is missing AND `wrong` is an
        # extra key (the body uses `extra="forbid"`, so the extra-key path
        # actually fires — Pydantic's default `extra="ignore"` would have
        # left only the missing-field error).
        response = _build_client().post("/needs-body", json={"wrong": 1})
        assert response.status_code == 422
        log_spy.warning.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=False)
        assert fields["http.response.status_code"] == 422
        assert fields["error.type"] == "ValidationError"
        assert fields["error_domain"] == "input"
        # The summary covers both per-field failures the request triggered.
        assert "field" in fields["detail"]
        assert "wrong" in fields["detail"]
        log_spy.error.assert_not_called()

    @pytest.mark.parametrize(
        "crafted_detail",
        [
            # A newline in the detail used to forge a second log line entirely — the worst case
            # for newline-delimited shippers (Loki, journald, CloudWatch) back when the API
            # flattened its own fields into one `key=value` run.
            "legit\nstatus=200 event=auth_success",
            # Whitespace plus `key=value` runs were the canonical logfmt forge.
            "hijack status=200 event=fake",
            # A carriage return alone was enough to corrupt a CRLF shipper.
            "legit\rstatus=200",
            # A bare quote used to close the quoted region early in a permissive parser.
            'has " a quote = inside',
        ],
    )
    def test_crafted_detail_stays_one_field_and_shapes_no_other(self, mocker: MockerFixture, crafted_detail: str) -> None:
        # `_log_api_authored_error` ships `document["detail"]`, and `detail` originates from caller
        # input on several routes (`raise_validation_error(str(exc))`, callback-URL rejections,
        # `_summarize_request_validation_error`'s per-field messages). The API renders none of it
        # any more: the value is handed to the runtime as one field, so it cannot forge a sibling
        # field and cannot reach the message, and the selected sink is what escapes it on the way
        # out. Pin that at the handler, so a route shipping some new caller-controlled field later
        # is covered without re-auditing this surface.
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        response = _build_client().get("/crafted-detail", params={"detail": crafted_detail})
        assert response.status_code == 422
        fields = _emitted_fields(log_spy, as_error=False)
        assert fields["detail"] == crafted_detail, f"the value was altered on the way to the record: {fields['detail']!r}"
        assert fields["http.response.status_code"] == 422, "a crafted detail overwrote a legitimate field"
        message = log_spy.warning.call_args.args[0]
        assert crafted_detail not in message, f"caller input reached the message: {message!r}"

    def test_async_execution_not_enabled_maps_to_501(self):
        # ``AsyncExecutionNotEnabledError`` carries ``runtime.unsupported``, whose registry entry declares 501 Not
        # Implemented: the failure is permanent under the current deployment rather than a transient runtime fault.
        response = _build_client().get("/async-execution-not-enabled")
        assert response.status_code == 501
        assert response.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
        body = response.json()
        # The body's ``status`` member agrees with the HTTP status.
        assert body["status"] == 501
        runtime_unsupported = error_code_spec(CoreCode.RUNTIME_UNSUPPORTED)
        assert body["code"] == CoreCode.RUNTIME_UNSUPPORTED
        assert body["title"] == runtime_unsupported.title
        assert body["type"] == runtime_unsupported.type_uri
        assert body["domain"] == "operator"
        assert body["detail"] == "This runtime lacks asynchronous execution, which the request needs."
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]

    def test_async_execution_not_enabled_logs_its_status(self, mocker: MockerFixture):
        # The record carries the status the client saw.
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        response = _build_client().get("/async-execution-not-enabled")
        assert response.status_code == 501
        log_spy.error.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=True)
        assert fields["http.response.status_code"] == 501
        assert fields["error.type"] == "AsyncExecutionNotEnabledError"
        assert fields["error.code"] == CoreCode.RUNTIME_UNSUPPORTED
        assert fields["error_domain"] == "config"

    def test_pipeline_run_id_conflict_maps_to_409(self):
        # ``PipelineManagerAlreadyExistsError`` carries ``pipelex.run.already_exists``, a client-visible conflict whose
        # registry entry declares 409, so callers can tell "this id is currently in use" apart from an internal failure.
        response = _build_client().get("/pipeline-run-id-conflict")
        assert response.status_code == 409
        assert response.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
        body = response.json()
        assert body["status"] == 409
        run_already_exists = error_code_spec(PipelexErrorCode.RUN_ALREADY_EXISTS)
        assert body["code"] == PipelexErrorCode.RUN_ALREADY_EXISTS
        assert body["title"] == run_already_exists.title
        assert body["type"] == run_already_exists.type_uri
        assert body["domain"] == "input"
        assert body["next_step"]["kind"] == "change_input"
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]

    @pytest.mark.parametrize("as_operator", [True, False], ids=["operator", "caller"])
    def test_method_package_symlink_maps_to_422(self, mocker: MockerFixture, as_operator: bool):
        # ``MethodPackageSymlinkError`` carries ``method.package_invalid``: a symlink in a fetched package is a rule
        # about the fetched content that its author fixes, not a server fault, so it answers 422 and logs at warning.
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        response = _build_client(as_operator=as_operator).get("/method-package-symlink")
        assert response.status_code == 422
        assert response.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
        body = response.json()
        assert body["status"] == 422
        assert body["code"] == CoreCode.METHOD_PACKAGE_INVALID
        assert body["domain"] == "method"
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]
        if as_operator:
            assert body["diagnostics"]["error_class"] == "MethodPackageSymlinkError"
            assert "contains a symlink ('vendored')" in body["diagnostics"]["message"]
        else:
            assert "diagnostics" not in body
        log_spy.warning.assert_called_once()
        log_spy.error.assert_not_called()

    def test_pipeline_run_id_conflict_logs_at_warning(self, mocker: MockerFixture):
        # A duplicate pipeline_run_id is a client-visible 409 conflict, not a
        # server fault: disposition is keyed off the final HTTP status, so it
        # logs at `warning` without a traceback — never `error` (which would
        # page or pollute error dashboards for a normal conflict). The record
        # still agrees with the status the client saw.
        log_spy = mocker.patch("pipelex_api.exception_handlers.log")
        response = _build_client().get("/pipeline-run-id-conflict")
        assert response.status_code == 409
        log_spy.warning.assert_called_once()
        log_spy.error.assert_not_called()
        fields = _emitted_fields(log_spy, as_error=False)
        assert fields["http.response.status_code"] == 409
        assert fields["error.type"] == "PipelineManagerAlreadyExistsError"
        assert fields["error.code"] == PipelexErrorCode.RUN_ALREADY_EXISTS
