"""`/validate` dispatches by orchestration_mode through the BundleValidatorRegistry (verdict-as-value).

Pins the dispatch+route mapping independent of any real backend, with a stub validator registered
for a non-direct mode (no `temporalio` import): the runner resolves the deployment's orchestration_mode,
dispatches to the validator the registry holds for it, and the route maps the *returned* verdict —
a `BundleValidationFailure` with validation items to a 200 `InvalidReport`, a returned failure with none
to the problem+json its code's status gives, and a raised fault to a 5xx. Also pins the no-validator case (`MissingBundleValidatorError`)
and that the route threads `orchestration_mode` into the same override policy `/start` uses (a forbidden
override is a 403). The `direct` path is covered end-to-end by the existing `/validate` suite; this proves
the dispatch is backend-agnostic, not direct-only.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mthds.protocol.problem.registry import CoreCode
from pipelex.base_exceptions import PipelexConfigError, ValidationErrorCategory, ValidationErrorItem
from pipelex.errors.bundle_validation_failure import BundleValidationFailure
from pipelex.errors.error_codes import error_code_spec
from pipelex.errors.problem import ProblemDiagnostics, ProblemView, make_problem
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.plugins.bundle_validator_registry import BundleValidatorRegistry
from pipelex.runtime_bridge.exceptions import MissingBundleValidatorError
from pipelex.system.caller_identity import CallerIdentity
from pytest_mock import MockerFixture

from pipelex_api.api_config import ApiConfig
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router
from pipelex_api.routes.pipelex.pipeline import ApiRunner
from tests.unit._constants import VALID_MTHDS

_PIPELINE_NS = "pipelex_api.routes.pipelex.pipeline"


class _StubBundleValidator:
    """A backend-agnostic stand-in validator: records its call, then returns or raises as configured."""

    def __init__(self, *, verdict: BundleValidationFailure | None = None, error: Exception | None = None) -> None:
        self._verdict = verdict
        self._error = error
        self.calls: list[dict[str, Any]] = []

    async def validate_bundles(
        self,
        *,
        mthds_contents: list[str] | None,
        mthds_sources: list[str] | None,
        allow_signatures: bool,
        library_dirs: Sequence[Path] | None,
        caller_identity: CallerIdentity | None,
        graph_pipe_code: str | None,
        submitted_files: Mapping[str, bytes] | None,
        method_dir: Path | None,
        methods_dirs: Sequence[Path] | None,
    ) -> BundleValidationFailure:
        self.calls.append(
            {
                "mthds_contents": mthds_contents,
                "mthds_sources": mthds_sources,
                "allow_signatures": allow_signatures,
                "library_dirs": library_dirs,
                "caller_identity": caller_identity,
                "graph_pipe_code": graph_pipe_code,
                "submitted_files": submitted_files,
                "method_dir": method_dir,
                "methods_dirs": methods_dirs,
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
        """A non-direct validator's returned failure with items is mapped to a 200 InvalidReport, threading the request."""
        invalid_verdict = BundleValidationFailure(
            problem=make_problem(code=CoreCode.METHOD_INVALID, view=ProblemView.OPERATOR),
            validation_errors=[ValidationErrorItem(category=ValidationErrorCategory.BLUEPRINT_VALIDATION, message="bad ref")],
        )
        stub = _StubBundleValidator(verdict=invalid_verdict)
        _register_stub_for_temporal(mocker, stub)

        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS], "allow_signatures": True})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        assert body["validation_errors"] == [{"category": ValidationErrorCategory.BLUEPRINT_VALIDATION, "message": "bad ref"}]
        assert body["message"] == error_code_spec(CoreCode.METHOD_INVALID).detail
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

        # The deployment's own configuration: its code's 500, and in the caller's view nothing of its message.
        assert response.status_code == 500, response.text
        assert response.headers["content-type"].startswith("application/problem+json")
        body = response.json()
        assert body["code"] == PipelexErrorCode.CONFIG_INVALID
        assert body["domain"] == "operator"
        assert "is_valid" not in body
        assert "diagnostics" not in body
        assert "backend wiring fault" not in response.text

    def test_returned_failure_without_items_maps_to_its_codes_problem(self, mocker: MockerFixture) -> None:
        """A registry-backed validator can return a backend fault, not an invalid-bundle verdict: its code's status, in the caller's view."""
        backend_fault = BundleValidationFailure(
            problem=make_problem(
                code=CoreCode.RUNTIME_UNAVAILABLE,
                view=ProblemView.OPERATOR,
                diagnostics=ProblemDiagnostics(error_class="TemporalTransportError", message="validator backend unavailable"),
            ),
        )
        stub = _StubBundleValidator(verdict=backend_fault)
        _register_stub_for_temporal(mocker, stub)

        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS]})

        assert response.status_code == 503, response.text
        assert response.headers["content-type"].startswith("application/problem+json")
        body = response.json()
        assert body["code"] == CoreCode.RUNTIME_UNAVAILABLE
        assert body["status"] == 503
        assert body["retry"] == "yes"
        # Built in the operator's view by the validator, projected to the caller's by the route.
        assert "diagnostics" not in body
        assert "validator backend unavailable" not in response.text
        assert "is_valid" not in body
        assert "validation_errors" not in body
        assert "errors" not in body

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
        assert exc_info.value.resolve_error_code() == PipelexErrorCode.PLUGIN_NOT_FOUND

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
