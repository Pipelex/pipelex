"""Integration tests for the global FastAPI exception handlers.

These tests register the production handlers on a throwaway FastAPI app whose
routes raise straight through — `ApiError`, `RequestValidationError`,
`PipelexError`, a bare orchestrator-SDK transport error (handled via a synthetic
plugin-contributed mapper, proving the F3 seam without importing any orchestrator
SDK), and uncaught `Exception` each end up at their respective handler exactly
the way the real app routes them.
"""

import re
from typing import Any, cast

import pytest
from fastapi import APIRouter, FastAPI, Request
from fastapi.testclient import TestClient
from pipelex.base_exceptions import (
    INTERNAL_ERROR_PLACEHOLDER,
    DisclosureMode,
    ErrorDomain,
    ErrorReport,
    PipelexConfigError,
    PipelexError,
)
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserAction, UserActionKind
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.config import get_config
from pipelex.pipe_run.exceptions import AsyncExecutionNotEnabledError
from pipelex.pipeline.exceptions import PipelineManagerAlreadyExistsError
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.registrar import HttpErrorMapperFn, PluginOrigin, PluginRegistrar
from pipelex.system.exceptions import EnvVarNotFoundError
from pydantic import BaseModel, ConfigDict
from pytest_mock import MockerFixture
from typing_extensions import override

from api.error_types import ErrorType
from api.errors import raise_internal_server_error, raise_validation_error
from api.exception_handlers import API_ERROR_EVENT, register_exception_handlers
from api.middleware import REQUEST_ID_HEADER, RequestIdMiddleware
from api.problem_document import PROBLEM_JSON_MEDIA_TYPE
from api.security import RequestUser

# Crockford Base32, 26 chars — the ULID alphabet RequestIdMiddleware mints.
_ULID_RE = re.compile(r"\A[0-9A-HJKMNP-TV-Z]{26}\Z")


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


class _SimulatedLLMError(PipelexError):
    """A `PipelexError` whose report mimics a provider rate-limit (429) failure."""

    @override
    def to_error_report(self) -> ErrorReport:
        return ErrorReport(
            error_type="LLMCompletionError",
            message="OpenAI returned 429 (rate_limit_exceeded)",
            title="LLM completion error",
            type_uri="https://docs.pipelex.com/latest/errors/llm-completion-error/",
            error_category="transient",
            error_domain="runtime",
            retryable=True,
            user_action=UserAction(kind=UserActionKind.WAIT_AND_RETRY, detail="Retry after 12s."),
            model="gpt-4o-mini",
            provider="openai",
            provider_metadata=ProviderErrorMetadata(
                provider=ProviderName.OPENAI,
                sdk_exception_type="RateLimitError",
                status_code=429,
                retry_after_seconds=12.0,
                request_id="req_provider_abc",
            ),
        )


class _CorruptReportError(PipelexError):
    """A `PipelexError` whose `to_error_report` itself fails — the handler-of-handlers case."""

    @override
    def to_error_report(self) -> ErrorReport:
        msg = "to_error_report is deliberately broken"
        raise RuntimeError(msg)


class _CallerFacingInputError(PipelexError):
    """An `INPUT`-domain error whose message is genuine caller-facing copy.

    `_authors_caller_facing_message` makes STRICT disclosure keep the message
    verbatim — the projection pipelex applies to a `.mthds` syntax error.
    """

    error_domain = ErrorDomain.INPUT
    _authors_caller_facing_message = True


class _SyntheticTransportError(Exception):
    """A bare orchestrator-SDK-style transport error — NOT a `PipelexError`, no `temporalio`.

    Stands in for the kind of exception an orchestrator plugin contributes a mapper for (e.g.
    `temporalio.TemporalError`), so the F3 seam — plugin maps a bare transport exception to a
    structured `ErrorReport`, the API renders it — is exercised without importing any orchestrator SDK.
    """


class _SyntheticOrchestratorError(PipelexError):
    """An orchestrator failure that IS a `PipelexError` (carries its own `ErrorReport`).

    Stands in for e.g. the Temporal plugin's `WorkflowExecutionError`: Starlette's MRO walk resolves
    it to `handle_pipelex_error`, never to the transport mapper handler registered for a bare
    transport exception.
    """


def _synthetic_transport_to_report(exc: Exception) -> ErrorReport:
    """The mapper an orchestrator plugin would contribute: classify the bare transport fault.

    Mirrors the classification the (now plugin-owned) Temporal transport mapper produces — a
    retryable, `RUNTIME`-domain `transient` failure.
    """
    return ErrorReport(
        error_type="SyntheticTransportError",
        message=str(exc),
        title="Synthetic transport error",
        type_uri="https://docs.pipelex.com/latest/errors/synthetic-transport-error/",
        error_category="transient",
        error_domain=ErrorDomain.RUNTIME,
        retryable=True,
    )


def _synthetic_http_error_mappers() -> dict[type[Exception], HttpErrorMapperFn]:
    """Resolve a mapper the way an installed orchestrator plugin would — through the registrar SPI.

    Builds a `PluginRegistrar`, has a synthetic plugin contribute the mapper via
    `add_http_error_mapper`, and reads it back with `get_http_error_mappers` — exercising the real
    producer→consumer seam (the same one `api.main` drives at app construction) without installing a
    plugin or importing an orchestrator SDK.
    """
    registrar = PluginRegistrar(config=get_config())
    # `group=None` is what a built-in carries: the entry-point group is how an *external* plugin
    # declares its layer, and a built-in arrives under none — it is filed by layer in-tree instead.
    registrar.begin_plugin(name="synthetic-transport-plugin", origin=PluginOrigin.BUILTIN, targets_api=PLUGIN_API_VERSION, group=None)
    registrar.add_http_error_mapper(exc_type_provider=lambda: _SyntheticTransportError, to_error_report=_synthetic_transport_to_report)
    return registrar.get_http_error_mappers()


def _report_with_retry(*, status_code: int, retry_after_seconds: float | None) -> ErrorReport:
    """Build a provider-error report carrying a `retry_after_seconds` hint."""
    return ErrorReport(
        error_type="LLMCompletionError",
        message="provider error",
        title="LLM completion error",
        type_uri="https://docs.pipelex.com/latest/errors/llm-completion-error/",
        error_category="transient",
        error_domain="runtime",
        retryable=True,
        provider_metadata=ProviderErrorMetadata(
            provider=ProviderName.OPENAI,
            sdk_exception_type="RateLimitError",
            status_code=status_code,
            retry_after_seconds=retry_after_seconds,
        ),
    )


# Reports exercising every branch of `_retry_after_header`: a finite hint, the
# two non-finite values a provider could emit, a negative value, and a hint
# carried on a non-429 status (where `Retry-After` must not be emitted).
_RETRY_REPORTS: dict[str, ErrorReport] = {
    "finite": _report_with_retry(status_code=429, retry_after_seconds=12.4),
    "infinite": _report_with_retry(status_code=429, retry_after_seconds=float("inf")),
    "nan": _report_with_retry(status_code=429, retry_after_seconds=float("nan")),
    "negative": _report_with_retry(status_code=429, retry_after_seconds=-5.0),
    "non_429": _report_with_retry(status_code=503, retry_after_seconds=30.0),
}


class _CraftedRetryError(PipelexError):
    """A `PipelexError` whose report is selected by key — exercises `_retry_after_header`."""

    def __init__(self, report_key: str) -> None:
        super().__init__("crafted retry-after scenario")
        self._report = _RETRY_REPORTS[report_key]

    @override
    def to_error_report(self) -> ErrorReport:
        return self._report


# Route handlers are deliberately not underscore-prefixed: a private,
# decorator-only function reads as unused to the type checker.
_router = APIRouter()


@_router.get("/config-error")
async def config_error_route() -> None:
    msg = "the gateway config is missing"
    raise PipelexConfigError(msg)


@_router.get("/env-error")
async def env_error_route() -> None:
    msg = "Environment variable 'COMPLETION_CALLBACK_SECRET' is required but not set"
    raise EnvVarNotFoundError(msg)


@_router.get("/input-error")
async def input_error_route() -> None:
    msg = "your .mthds file has a syntax error on line 4"
    raise _CallerFacingInputError(msg)


@_router.get("/llm-error")
async def llm_error_route() -> None:
    msg = "simulated provider rate limit"
    raise _SimulatedLLMError(msg)


@_router.get("/corrupt-error")
async def corrupt_error_route() -> None:
    msg = "its report builder is broken"
    raise _CorruptReportError(msg)


@_router.get("/orchestrator-pipelex-error")
async def orchestrator_pipelex_error_route() -> None:
    msg = "the workflow failed"
    raise _SyntheticOrchestratorError(msg)


@_router.get("/async-execution-not-enabled")
async def async_execution_not_enabled_route() -> None:
    # Pipelex raises this when an async dispatch site is reached on a
    # deployment without an async execution backend enabled. The API maps it
    # to 501 Not Implemented (see ``_ERROR_TYPE_STATUS_OVERRIDES``).
    msg = "Asynchronous pipeline execution is not enabled on this deployment."
    raise AsyncExecutionNotEnabledError(msg)


@_router.get("/pipeline-run-id-conflict")
async def pipeline_run_id_conflict_route() -> None:
    # Pipelex raises this from ``add_new_pipeline`` when a submission reuses a
    # ``pipeline_run_id`` that is still registered (a genuinely concurrent
    # duplicate — completed/failed runs free their entry on the way out). The
    # API maps it to 409 Conflict (see ``_ERROR_TYPE_STATUS_OVERRIDES``).
    msg = "Pipeline some-run-id already exists"
    raise PipelineManagerAlreadyExistsError(msg)


@_router.get("/synthetic-transport-error")
async def synthetic_transport_error_route() -> None:
    msg = "orchestrator cluster unreachable"
    raise _SyntheticTransportError(msg)


@_router.get("/unexpected-error")
async def unexpected_error_route() -> None:
    msg = "something nobody anticipated"
    raise RuntimeError(msg)


@_router.get("/crafted-retry/{report_key}")
async def crafted_retry_route(report_key: str) -> None:
    raise _CraftedRetryError(report_key)


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
# path-safe id (`api.security.is_safe_user_id`), so the routes mirror real
# auth state rather than a placeholder string.
_TEST_USER_ID = "00000000-0000-0000-0000-000000000001"


def _bind_test_user(request: Request) -> None:
    """Set `request.state.user` the same shape `api.security._set_request_user` would.

    The throwaway app does not run the real auth dependency — these routes stand
    in for "auth succeeded" so the error-log enrichment can be exercised
    without dragging in JWT validation.
    """
    request.state.user = RequestUser(user_id=_TEST_USER_ID)


# Canonical body-derived identifiers for the pipeline-state routes — bound on
# `request.state` the same way `api.routes.pipelex.pipeline._parse_request`
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
    msg = "the gateway config is missing"
    raise PipelexConfigError(msg)


@_router.get("/authenticated-api-input-error")
async def authenticated_api_input_error_route(request: Request) -> None:
    _bind_test_user(request)
    raise_validation_error("a caller-side mistake")


@_router.get("/authenticated-unexpected-error")
async def authenticated_unexpected_error_route(request: Request) -> None:
    _bind_test_user(request)
    msg = "something nobody anticipated"
    raise RuntimeError(msg)


@_router.get("/pipeline-state-pipelex-error")
async def run_state_pipelex_error_route(request: Request) -> None:
    # Stand-in for the production flow: a body went through `_parse_request`
    # (state bound), then pipelex raised a `PipelexError` further down the
    # stack. Exercises `_log_error_report`.
    _bind_test_run_state(request)
    msg = "the gateway config is missing"
    raise PipelexConfigError(msg)


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
    msg = "something nobody anticipated"
    raise RuntimeError(msg)


def _build_client(
    *,
    raise_server_exceptions: bool = True,
    disclosure_mode: DisclosureMode = DisclosureMode.VERBOSE,
    http_error_mappers: dict[type[Exception], HttpErrorMapperFn] | None = None,
) -> TestClient:
    """Wire a throwaway app with the production handlers and request-id middleware.

    `raise_server_exceptions` must be `False` for tests that hit the catch-all
    handler: Starlette's `ServerErrorMiddleware` always re-raises after running
    its handler, so the `TestClient` would otherwise surface the exception
    instead of the sanitized response. `disclosure_mode` is the value
    `register_exception_handlers` captures in the closures it registers for
    `PipelexError` / the mapper handlers; the default mirrors production
    (VERBOSE), tests that exercise STRICT redaction pass it explicitly.
    `http_error_mappers` are the orchestrator-plugin mappers to register a
    transport handler per `exc_type` for — defaults to none (the agnostic base).
    """
    app = FastAPI()
    register_exception_handlers(app, disclosure_mode=disclosure_mode, http_error_mappers=http_error_mappers)
    app.include_router(_router)
    return TestClient(RequestIdMiddleware(app), raise_server_exceptions=raise_server_exceptions)


class TestExceptionHandlers:
    def test_pipelex_error_produces_problem_json(self):
        response = _build_client().get("/config-error")
        assert response.status_code == 500
        assert response.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
        body = response.json()
        assert body["type"].endswith("/pipelex-config-error/")
        assert body["title"] == "Pipelex config"
        assert body["status"] == 500
        assert body["detail"] == "the gateway config is missing"
        assert body["error_type"] == "PipelexConfigError"
        assert body["error_domain"] == "config"
        assert body["instance"] == "/config-error"
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]

    def test_env_var_not_found_error_is_config_500(self):
        # EnvVarNotFoundError is a ToolError that pipelex classifies under the
        # config domain: a missing required env var is an operator-fixable
        # misconfiguration, so it maps to HTTP 500 with error_domain "config".
        response = _build_client().get("/env-error")
        assert response.status_code == 500
        body = response.json()
        assert "COMPLETION_CALLBACK_SECRET" in body["detail"]
        assert body["error_type"] == "EnvVarNotFoundError"
        assert body["error_domain"] == "config"

    def test_strict_disclosure_redacts_config_preserves_input(self):
        # The handler forwards the disclosure mode it was registered under
        # unchanged; pipelex owns the redaction. STRICT redacts a
        # non-caller-facing message and keeps a caller-facing one.
        client = _build_client(disclosure_mode=DisclosureMode.STRICT)

        config_response = client.get("/config-error")
        assert config_response.status_code == 500
        assert config_response.json()["detail"] == INTERNAL_ERROR_PLACEHOLDER
        assert "the gateway config is missing" not in config_response.text

        input_response = client.get("/input-error")
        assert input_response.status_code == 422
        assert input_response.json()["detail"] == "your .mthds file has a syntax error on line 4"

    def test_provider_rate_limit_emits_retry_after(self):
        response = _build_client().get("/llm-error")
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "12"
        body = response.json()
        assert body["error_type"] == "LLMCompletionError"
        assert body["retryable"] is True
        assert body["provider_metadata"]["status_code"] == 429

    @pytest.mark.parametrize(
        ("report_key", "expected_status", "expected_retry_after"),
        [
            ("finite", 429, "13"),  # 12.4 rounds up
            ("infinite", 429, None),  # non-finite is dropped — no crash, no header
            ("nan", 429, None),  # non-finite is dropped — no crash, no header
            ("negative", 429, "0"),  # clamped to a non-negative integer
            ("non_429", 500, None),  # the hint never rides a non-429 response
        ],
    )
    def test_retry_after_header_is_guarded(self, report_key: str, expected_status: int, expected_retry_after: str | None):
        response = _build_client().get(f"/crafted-retry/{report_key}")
        assert response.status_code == expected_status
        if expected_retry_after is None:
            assert "retry-after" not in response.headers
        else:
            assert response.headers["Retry-After"] == expected_retry_after

    def test_unexpected_error_discloses_class_and_message_under_verbose(self):
        # The catch-all honors the disclosure mode like every other handler.
        # Under VERBOSE an unclassified failure is the one error a caller cannot
        # diagnose from a request id alone, so `detail` names it outright —
        # otherwise a deployment that opted into disclosure would still hit a
        # dead end here.
        response = _build_client(raise_server_exceptions=False).get("/unexpected-error")
        assert response.status_code == 500
        assert response.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
        body = response.json()
        assert body["error_type"] == "InternalServerError"
        assert body["error_domain"] == "runtime"
        assert body["retryable"] is False
        assert body["type"].endswith("/internal-server-error/")
        assert body["instance"] == "/unexpected-error"
        assert body["error_category"] == "unknown"
        assert body["detail"] == "RuntimeError: something nobody anticipated"

    def test_unexpected_error_is_sanitized_under_strict(self):
        # STRICT still redacts: a deployment that wants nothing leaked keeps
        # exactly the old sanitized body — no class name, no `str(exc)`.
        client = _build_client(disclosure_mode=DisclosureMode.STRICT, raise_server_exceptions=False)
        response = client.get("/unexpected-error")
        assert response.status_code == 500
        body = response.json()
        assert body["error_type"] == "InternalServerError"
        assert body["error_category"] == "unknown"
        assert body["detail"] == "An unexpected error occurred. The request id is included for support."
        assert "RuntimeError" not in response.text
        assert "something nobody anticipated" not in response.text

    def test_unexpected_error_never_leaks_a_traceback(self):
        # Disclosure is the message, never the stack: a traceback stays an
        # operator-log artifact in BOTH modes.
        for mode in (DisclosureMode.VERBOSE, DisclosureMode.STRICT):
            response = _build_client(disclosure_mode=mode, raise_server_exceptions=False).get("/unexpected-error")
            assert "Traceback" not in response.text
            assert "unexpected_error_route" not in response.text

    def test_orchestrator_error_dispatch(self):
        # The F3 seam: a synthetic plugin contributes a transport mapper through the registrar SPI,
        # the app registers one handler per mapped exc_type, and a bare transport error renders the
        # plugin's classified ErrorReport — all without importing any orchestrator SDK.
        client = _build_client(http_error_mappers=_synthetic_http_error_mappers())

        # An orchestrator failure that IS a PipelexError — routed to the PipelexError handler (its
        # error_type is the class name), NOT the transport mapper handler.
        pipelex_response = client.get("/orchestrator-pipelex-error")
        assert pipelex_response.status_code == 500
        assert pipelex_response.json()["error_type"] == "_SyntheticOrchestratorError"

        # A bare transport error — routed to the plugin's mapper-backed handler, which renders the
        # transport-transient classification the mapper produced.
        transport_response = client.get("/synthetic-transport-error")
        assert transport_response.status_code == 500
        transport_body = transport_response.json()
        assert transport_body["error_type"] == "SyntheticTransportError"
        assert transport_body["error_category"] == "transient"
        assert transport_body["retryable"] is True

    def test_unmapped_transport_error_falls_back_to_catch_all_500(self):
        # Without the orchestrator plugin's mapper (the agnostic base), the same bare transport error
        # has no dedicated handler and collapses to the catch-all 500 — which under VERBOSE still
        # tells the caller which transport class failed and why.
        response = _build_client(raise_server_exceptions=False).get("/synthetic-transport-error")
        assert response.status_code == 500
        body = response.json()
        assert body["error_type"] == "InternalServerError"
        assert body["detail"] == "_SyntheticTransportError: orchestrator cluster unreachable"

    def test_handler_of_handlers_catches_corrupt_report(self):
        # When to_error_report() itself raises, the failure escapes the
        # PipelexError handler; ServerErrorMiddleware funnels it into the
        # catch-all — a real 500 body, never a bodyless default. The disclosed
        # class is the one raised *by the broken handler*, not the original.
        response = _build_client(raise_server_exceptions=False).get("/corrupt-error")
        assert response.status_code == 500
        body = response.json()
        assert body["error_type"] == "InternalServerError"
        assert body["error_category"] == "unknown"

    @pytest.mark.parametrize(
        ("method", "path", "json_body", "expected_status"),
        [
            ("GET", "/config-error", None, 500),
            ("GET", "/env-error", None, 500),
            ("GET", "/input-error", None, 422),
            ("GET", "/llm-error", None, 429),
            ("GET", "/orchestrator-pipelex-error", None, 500),
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

    def test_api_authored_500_emits_structured_error_record(self, mocker: MockerFixture):
        # Without `handle_api_error` logging, an `ApiError`-shaped 500 produces
        # zero operator output (`/version`'s `PackageNotFoundError →
        # raise_internal_server_error` is the canonical silent case). Assert
        # the handler emits one `api_error` record at `error` level whose fields
        # mirror the response — the same set `_log_error_report` ships for a
        # pipelex-derived 500, so a downstream sink queries them uniformly.
        log_spy = mocker.patch("api.exception_handlers.log")
        response = _build_client().get("/api-config-error")
        assert response.status_code == 500
        log_spy.error.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=True)
        assert fields["event"] == API_ERROR_EVENT
        assert fields["status"] == 500
        assert fields["error_type"] == "ServerMisconfigured"
        assert fields["error_domain"] == "config"
        assert fields["retryable"] is False
        assert fields["route"] == "/api-config-error"
        # The operator-facing cause rides a field of its own and never reaches the message, which
        # is what stops a crafted value from shaping the rendered line at all.
        assert fields["detail"] == "the configuration is broken"
        assert log_spy.error.call_args.kwargs["include_exception"] is True
        log_spy.warning.assert_not_called()

    def test_api_authored_4xx_emits_structured_warning_record(self, mocker: MockerFixture):
        # Mirror at the warning level: an INPUT-domain `ApiError` is a caller
        # mistake, not an operator fault, so it logs at `warning` without a
        # traceback — same disposition rule `_log_error_report` uses.
        log_spy = mocker.patch("api.exception_handlers.log")
        response = _build_client().get("/api-input-error")
        assert response.status_code == 422
        log_spy.warning.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=False)
        assert fields["event"] == API_ERROR_EVENT
        assert fields["status"] == 422
        assert fields["error_type"] == "ValidationError"
        assert fields["error_domain"] == "input"
        assert fields["retryable"] is False
        assert fields["detail"] == "a caller-side mistake"
        log_spy.error.assert_not_called()

    def test_the_summary_message_names_the_status_and_the_error_type(self, mocker: MockerFixture):
        # The message is built from server-authored values alone, so it stays a stable sentence
        # whatever a caller sent; everything variable is a field beside it.
        log_spy = mocker.patch("api.exception_handlers.log")
        assert _build_client().get("/api-config-error").status_code == 500
        assert log_spy.error.call_args.args[0] == "API error 500: ServerMisconfigured"

    def test_user_id_rides_authenticated_pipelex_error_record(self, mocker: MockerFixture):
        # Phase 3 deleted the per-route `log.error(... user=...)` lines on
        # storage / pipeline-backend failures; the global handler now reads
        # `request.state.user` so the operator can still tie a `PipelexError`
        # to the caller through the record alone — no correlating across
        # records on `request_id` required.
        log_spy = mocker.patch("api.exception_handlers.log")
        response = _build_client().get("/authenticated-config-error")
        assert response.status_code == 500
        log_spy.error.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=True)
        assert fields["user_id"] == _TEST_USER_ID
        assert fields["error_type"] == "PipelexConfigError"

    def test_user_id_rides_authenticated_api_authored_record(self, mocker: MockerFixture):
        # `handle_api_error` covers the API-authored 4xx surface (storage's
        # `raise_bad_request`, `raise_forbidden`, `raise_payload_too_large`;
        # uploader's same set). It must ride the same `user_id` correlation
        # `_log_error_report` does so the contract is uniform — a caller
        # mistake and a backend failure both name the caller.
        log_spy = mocker.patch("api.exception_handlers.log")
        response = _build_client().get("/authenticated-api-input-error")
        assert response.status_code == 422
        log_spy.warning.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=False)
        assert fields["user_id"] == _TEST_USER_ID
        assert fields["error_type"] == "ValidationError"

    def test_user_id_rides_authenticated_unexpected_error_record(self, mocker: MockerFixture):
        # The catch-all 500 (`handle_unexpected_error`) is the one place a
        # missing `user_id` is most expensive — by definition the failure
        # was not classifiable upstream — so the same enrichment fires here.
        log_spy = mocker.patch("api.exception_handlers.log")
        response = _build_client(raise_server_exceptions=False).get("/authenticated-unexpected-error")
        assert response.status_code == 500
        log_spy.error.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=True)
        assert fields["user_id"] == _TEST_USER_ID
        assert fields["error_type"] == "RuntimeError"

    def test_user_id_absent_from_unauthenticated_error_record(self, mocker: MockerFixture):
        # Pre-auth paths, and a deployment with no user model, have no `request.state.user`;
        # `_user_id_of` returns `None` and `_emit_api_error` drops `None`-valued fields, so the
        # record carries no `user_id` attribute at all — never a null, which a query filtering on
        # presence would read as an answer.
        log_spy = mocker.patch("api.exception_handlers.log")
        response = _build_client().get("/config-error")
        assert response.status_code == 500
        log_spy.error.assert_called_once()
        assert "user_id" not in _emitted_fields(log_spy, as_error=True)

    def test_run_state_rides_pipelex_error_record(self, mocker: MockerFixture):
        # `_parse_request` binds `pipe_code` / `pipeline_run_id` on
        # `request.state` so a downstream pipelex failure is tied to the
        # specific pipe and run id without each backend frame having to forward
        # them. Same mechanism as `user_id` (request.state + a `_*_of` getter
        # in the handler), now extended to the body-derived identifiers — the
        # last piece of Checkpoint B reconciliation #4.
        log_spy = mocker.patch("api.exception_handlers.log")
        response = _build_client().get("/pipeline-state-pipelex-error")
        assert response.status_code == 500
        log_spy.error.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=True)
        assert fields["pipe_code"] == _TEST_PIPE_CODE
        assert fields["pipeline_run_id"] == _TEST_RUN_ID
        assert fields["error_type"] == "PipelexConfigError"

    def test_run_state_rides_api_authored_record(self, mocker: MockerFixture):
        # API-authored 4xx surface: `raise_validation_error` raised from a
        # route that has already bound pipe state must ship the same fields,
        # so the operator record is uniform across the validation and the
        # pipelex-domain failure surfaces.
        log_spy = mocker.patch("api.exception_handlers.log")
        response = _build_client().get("/pipeline-state-api-input-error")
        assert response.status_code == 422
        log_spy.warning.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=False)
        assert fields["pipe_code"] == _TEST_PIPE_CODE
        assert fields["pipeline_run_id"] == _TEST_RUN_ID
        assert fields["error_type"] == "ValidationError"

    def test_run_state_rides_unexpected_error_record(self, mocker: MockerFixture):
        # The catch-all 500 is the most operationally expensive case for a
        # missing pipe-state field — by definition the failure was not
        # classifiable upstream, so the identifiers on the record are the
        # operator's only starting point for which pipe and which run were
        # in flight.
        log_spy = mocker.patch("api.exception_handlers.log")
        response = _build_client(raise_server_exceptions=False).get("/pipeline-state-unexpected-error")
        assert response.status_code == 500
        log_spy.error.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=True)
        assert fields["pipe_code"] == _TEST_PIPE_CODE
        assert fields["pipeline_run_id"] == _TEST_RUN_ID
        assert fields["error_type"] == "RuntimeError"

    def test_run_state_absent_when_parse_request_did_not_bind(self, mocker: MockerFixture):
        # A route that didn't go through `_parse_request` (here: `/config-error`,
        # a GET that never touches the body) has no `pipe_code` /
        # `pipeline_run_id` on `request.state`. The getters return `None` and
        # `_emit_api_error` drops those, so the record carries neither attribute.
        # Same defensive posture as `test_user_id_absent_from_unauthenticated_error_record`.
        log_spy = mocker.patch("api.exception_handlers.log")
        response = _build_client().get("/config-error")
        assert response.status_code == 500
        log_spy.error.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=True)
        assert "pipe_code" not in fields
        assert "pipeline_run_id" not in fields

    def test_request_validation_error_emits_structured_warning_record(self, mocker: MockerFixture):
        # FastAPI's automatic-validation 422 goes through
        # `handle_request_validation_error`, not `handle_api_error`, but emits
        # the same `api_error` record so the surface is uniform — whichever code
        # path rejects a caller-input failure, the operator record is identical.
        log_spy = mocker.patch("api.exception_handlers.log")
        # `{"wrong": 1}` triggers FastAPI's automatic validation failure on
        # `_RequestValidationBody`: `field` is missing AND `wrong` is an
        # extra key (the body uses `extra="forbid"`, so the extra-key path
        # actually fires — Pydantic's default `extra="ignore"` would have
        # left only the missing-field error).
        response = _build_client().post("/needs-body", json={"wrong": 1})
        assert response.status_code == 422
        log_spy.warning.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=False)
        assert fields["event"] == API_ERROR_EVENT
        assert fields["status"] == 422
        assert fields["error_type"] == "ValidationError"
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
        log_spy = mocker.patch("api.exception_handlers.log")
        response = _build_client().get("/crafted-detail", params={"detail": crafted_detail})
        assert response.status_code == 422
        fields = _emitted_fields(log_spy, as_error=False)
        assert fields["detail"] == crafted_detail, f"the value was altered on the way to the record: {fields['detail']!r}"
        assert fields["event"] == API_ERROR_EVENT, "a crafted detail overwrote a legitimate field"
        assert fields["status"] == 422, "a crafted detail overwrote a legitimate field"
        message = log_spy.warning.call_args.args[0]
        assert crafted_detail not in message, f"caller input reached the message: {message!r}"

    def test_async_execution_not_enabled_maps_to_501(self):
        # The pipelex-side ``AsyncExecutionNotEnabledError`` reports as
        # ``CONFIG``-domain (-> 500 under the default mapping), but the
        # API layer overrides it to 501 Not Implemented. 501 is more precise
        # for "this server does not provide async execution": it tells clients
        # the failure is permanent under the current deployment rather than a
        # transient runtime fault.
        response = _build_client().get("/async-execution-not-enabled")
        assert response.status_code == 501
        assert response.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
        body = response.json()
        # The body's ``status`` member must agree with the HTTP status — if
        # the override path only bumped the header status and left the body at
        # 500, RFC 7807-aware clients would see a contradictory document.
        assert body["status"] == 501
        assert body["title"] == "Async execution not enabled"
        assert body["error_type"] == "AsyncExecutionNotEnabledError"
        assert body["error_domain"] == "config"
        assert body["instance"] == "/async-execution-not-enabled"
        assert body["type"].endswith("/async-execution-not-enabled-error/")
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]

    def test_async_execution_not_enabled_logs_post_override_status(self, mocker: MockerFixture):
        # ``_log_error_report`` receives the overridden status so the operator
        # record agrees with what the client actually saw. Without the
        # ``status=`` plumbing the record would carry 500 (the report's domain
        # default) while the response shipped 501 — a silent disagreement
        # between the two surfaces. Pin the alignment.
        log_spy = mocker.patch("api.exception_handlers.log")
        response = _build_client().get("/async-execution-not-enabled")
        assert response.status_code == 501
        log_spy.error.assert_called_once()
        fields = _emitted_fields(log_spy, as_error=True)
        assert fields["event"] == API_ERROR_EVENT
        assert fields["status"] == 501
        assert fields["error_type"] == "AsyncExecutionNotEnabledError"
        assert fields["error_domain"] == "config"

    def test_pipeline_run_id_conflict_maps_to_409(self):
        # ``PipelineManagerAlreadyExistsError`` carries no ``error_domain``
        # (-> 500 under the default mapping), but a duplicate ``pipeline_run_id``
        # is a client-visible conflict, not a server fault: the API overrides it
        # to 409 Conflict so callers can tell "this id is currently in use"
        # (resubmit after the in-flight run finishes, or pick a fresh id) apart
        # from a real internal failure.
        response = _build_client().get("/pipeline-run-id-conflict")
        assert response.status_code == 409
        assert response.headers["content-type"] == PROBLEM_JSON_MEDIA_TYPE
        body = response.json()
        # The body's ``status`` member must agree with the HTTP status (same
        # RFC 7807 agreement contract as the 501 override above).
        assert body["status"] == 409
        assert body["error_type"] == "PipelineManagerAlreadyExistsError"
        assert body["title"] == "Pipeline manager already exists"
        assert body["instance"] == "/pipeline-run-id-conflict"
        assert body["type"].endswith("/pipeline-manager-already-exists-error/")
        assert body["request_id"] == response.headers[REQUEST_ID_HEADER]

    def test_pipeline_run_id_conflict_logs_at_warning_post_override_status(self, mocker: MockerFixture):
        # A duplicate pipeline_run_id is a client-visible 409 conflict, not a
        # server fault: disposition is keyed off the final HTTP status, so it
        # logs at `warning` without a traceback — never `error` (which would
        # page or pollute error dashboards for a normal conflict). The record
        # still agrees with the status the client saw.
        log_spy = mocker.patch("api.exception_handlers.log")
        response = _build_client().get("/pipeline-run-id-conflict")
        assert response.status_code == 409
        log_spy.warning.assert_called_once()
        log_spy.error.assert_not_called()
        fields = _emitted_fields(log_spy, as_error=False)
        assert fields["event"] == API_ERROR_EVENT
        assert fields["status"] == 409
        assert fields["error_type"] == "PipelineManagerAlreadyExistsError"
