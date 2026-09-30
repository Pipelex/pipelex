"""`/validate` dispatches by orchestration_mode through the BundleValidatorRegistry (verdict-as-value).

Pins the dispatch+route mapping independent of any real backend, with a stub validator registered
for a non-direct mode (no `temporalio` import): the runner resolves the deployment's orchestration_mode,
dispatches to the validator the registry holds for it, and the route maps the *returned* verdict —
an `ErrorReport` with validation diagnostics to a 200 `InvalidReport`, a returned backend fault report
to problem+json, and a raised fault to a 5xx. Also pins the no-validator case (`MissingBundleValidatorError`)
and that the route threads `orchestration_mode` into the same override policy `/start` uses (a forbidden
override is a 403). The `direct` path is covered end-to-end by the existing `/validate` suite; this proves
the dispatch is backend-agnostic, not direct-only.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipelex.base_exceptions import ErrorDomain, ErrorReport, PipelexConfigError, ValidationErrorCategory, ValidationErrorItem
from pipelex.plugins.bundle_validator_registry import BundleValidatorRegistry
from pipelex.runtime_bridge.exceptions import MissingBundleValidatorError
from pipelex.system.caller_identity import CallerIdentity
from pytest_mock import MockerFixture

from api.api_config import ApiConfig
from api.exception_handlers import register_exception_handlers
from api.routes import router as api_router
from api.routes.pipelex.pipeline import ApiRunner
from tests.unit._constants import VALID_MTHDS

_PIPELINE_NS = "api.routes.pipelex.pipeline"


class _StubBundleValidator:
    """A backend-agnostic stand-in validator: records its call, then returns or raises as configured."""

    def __init__(self, *, verdict: ErrorReport | None = None, error: Exception | None = None) -> None:
        self._verdict = verdict
        self._error = error
        self.calls: list[dict[str, Any]] = []

    async def validate_bundles(
        self,
        *,
        mthds_contents: list[str],
        mthds_sources: list[str] | None,
        allow_signatures: bool,
        library_dirs: Sequence[Path] | None,
        caller_identity: CallerIdentity | None,
        graph_pipe_code: str | None,
    ) -> ErrorReport:
        self.calls.append(
            {
                "mthds_contents": mthds_contents,
                "mthds_sources": mthds_sources,
                "allow_signatures": allow_signatures,
                "library_dirs": library_dirs,
                "caller_identity": caller_identity,
                "graph_pipe_code": graph_pipe_code,
            }
        )
        if self._error is not None:
            raise self._error
        assert self._verdict is not None
        return self._verdict


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


def _register_stub_for_temporal(mocker: MockerFixture, stub: _StubBundleValidator) -> None:
    """Make the deployment default to the `temporal` mode and register `stub` for it — no temporalio import.

    Patches the api config (so the real `resolve_orchestration_mode` returns the temporal mode by default)
    and the bundle-validator registry (so the route's mode lookup finds the stub).
    """
    temporal_config = ApiConfig(orchestration_mode="temporal", allow_request_orchestration_mode_override=False)
    mocker.patch(f"{_PIPELINE_NS}.get_api_config", return_value=temporal_config)
    registry = BundleValidatorRegistry({"temporal": stub})
    mocker.patch(f"{_PIPELINE_NS}.get_bundle_validator_registry", return_value=registry)


class TestValidateDispatch:
    def test_non_direct_validators_invalid_verdict_maps_to_200_invalid_report(self, mocker: MockerFixture) -> None:
        """A non-direct validator's returned ErrorReport is mapped to a 200 InvalidReport, threading the request."""
        invalid_verdict = ErrorReport(
            error_type="ValidateBundleError",
            message="bundle is invalid",
            title="Validate bundle error",
            type_uri="https://errors.pipelex.com/validate-bundle-error/",
            validation_errors=[ValidationErrorItem(category=ValidationErrorCategory.BLUEPRINT_VALIDATION, message="bad ref")],
        )
        stub = _StubBundleValidator(verdict=invalid_verdict)
        _register_stub_for_temporal(mocker, stub)

        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS], "allow_signatures": True})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        assert any(item["category"] == ValidationErrorCategory.BLUEPRINT_VALIDATION for item in body["validation_errors"])
        # The dispatch reached the registered non-direct validator, with the request threaded through.
        assert len(stub.calls) == 1
        assert stub.calls[0]["mthds_contents"] == [VALID_MTHDS]
        assert stub.calls[0]["allow_signatures"] is True

    def test_validator_fault_propagates_as_5xx(self, mocker: MockerFixture) -> None:
        """A validator that raises a genuine fault (no verdict produced) propagates to the global 5xx handler."""
        stub = _StubBundleValidator(error=PipelexConfigError("backend wiring fault"))
        _register_stub_for_temporal(mocker, stub)

        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS]})

        assert response.status_code >= 500, response.text
        assert response.headers["content-type"].startswith("application/problem+json")
        assert "is_valid" not in response.json()

    def test_returned_non_verdict_error_report_maps_to_problem_json(self, mocker: MockerFixture) -> None:
        """A registry-backed validator can return a classified backend fault report, not an invalid-bundle verdict."""
        backend_fault = ErrorReport(
            error_type="TemporalTransportError",
            message="validator backend unavailable",
            title="Temporal transport error",
            type_uri="https://errors.pipelex.com/temporal-transport-error/",
            error_domain=ErrorDomain.CONFIG,
        )
        stub = _StubBundleValidator(verdict=backend_fault)
        _register_stub_for_temporal(mocker, stub)

        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS]})

        assert response.status_code == 500, response.text
        assert response.headers["content-type"].startswith("application/problem+json")
        body = response.json()
        assert body["error_type"] == "TemporalTransportError"
        assert body["error_domain"] == ErrorDomain.CONFIG
        assert body["status"] == 500
        assert "is_valid" not in body
        assert "validation_errors" not in body

    @pytest.mark.asyncio
    async def test_missing_validator_for_resolved_mode_raises(self, mocker: MockerFixture) -> None:
        """A resolved mode with no registered validator fails loud with MissingBundleValidatorError."""
        mocker.patch(f"{_PIPELINE_NS}.get_bundle_validator_registry", return_value=BundleValidatorRegistry({}))

        with pytest.raises(MissingBundleValidatorError) as exc_info:
            await ApiRunner().validate_verdict(
                mthds_contents=[VALID_MTHDS],
                mthds_sources=None,
                allow_signatures=False,
                requested_orchestration_mode=None,
                graph_pipe_code=None,
            )
        assert exc_info.value.mode == "direct"

    def test_forbidden_orchestration_mode_override_is_a_403(self) -> None:
        """The route threads orchestration_mode into the same override policy /start uses: a forbidden override is a 403."""
        client = _build_client()
        # Packaged default is `direct` with override OFF; forcing a different backend is refused before dispatch.
        response = client.post(
            "/v1/validate",
            json={"mthds_contents": [VALID_MTHDS], "orchestration_mode": "temporal"},
        )

        assert response.status_code == 403, response.text
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.json()["error_type"] == "OrchestrationModeOverrideForbidden"
