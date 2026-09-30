"""`/validate` and `/build/runner` hand the runtime the caller their validation sweep is done for.

A validation is not a run, but its dry runs and its `pipe_dry_run` event are still telemetry, and
the runtime attributes them to the `CallerIdentity` it is handed. Every failure on this path is
SILENT by construction: a keyword left out of `ApiRunner(...)` or `validate_bundle(...)` still
answers 200, and the only symptom is that the sweep lands in PostHog under the deployment's
constant id instead of the caller. So these tests read the caller off the call the runtime
actually received — a recording validator for the dispatched `/validate`, the real in-process
entry points (wrapped, not replaced) for the direct path and for `/build/runner`.

The user comes from `request.state.user`, which the auth layer sets; a tiny middleware stands in
for it here. The groups come from the body and are refused at the wire exactly as on a run.
"""

from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from pipelex.base_exceptions import ErrorReport, ValidationErrorCategory, ValidationErrorItem
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.pipeline.validate_in_process import validate_bundles_in_process
from pipelex.plugins.bundle_validator_registry import BundleValidatorRegistry
from pipelex.system.caller_identity import CallerIdentity
from pipelex.system.storage_scope import SINGLE_TENANT_USER_ID
from pytest_mock import MockerFixture

from api.api_config import ApiConfig
from api.exception_handlers import register_exception_handlers
from api.routes import router as api_router
from api.security import RequestUser
from tests.unit._constants import STUB_METHOD_ADDRESS, VALID_MTHDS

_PIPELINE_NS = "api.routes.pipelex.pipeline"
_RUNNER_NS = "api.routes.pipelex.build.runner"
_DIRECT_VALIDATOR_NS = "pipelex.pipeline.direct_bundle_validator"
_MODE = "temporal"
_USER_ID = "user_42"
_GROUPS = {"organization": "org_acme", "workspace": "ws-42"}
_METHOD_REF = f"{STUB_METHOD_ADDRESS}@v0.1.0"

_BAD_GROUPS = [
    pytest.param({"Organization": "org_acme"}, id="type-not-snake-case"),
    pytest.param({"organization": "org acme"}, id="key-with-space"),
    pytest.param({"organization": ""}, id="empty-key"),
    pytest.param({f"group_{idx}": "org_acme" for idx in range(6)}, id="over-the-entry-cap"),
    pytest.param({"organization": 42}, id="non-string-key"),
    pytest.param(["organization"], id="not-a-mapping"),
]


class _RecordingBundleValidator:
    """Records the caller of every validation dispatched to it, then answers an invalid verdict."""

    def __init__(self) -> None:
        self.caller_identities: list[CallerIdentity | None] = []

    async def validate_bundles(
        self,
        *,
        mthds_contents: list[str],  # noqa: ARG002
        mthds_sources: list[str] | None,  # noqa: ARG002
        allow_signatures: bool,  # noqa: ARG002
        library_dirs: Sequence[Path] | None,  # noqa: ARG002
        caller_identity: CallerIdentity | None,
        graph_pipe_code: str | None,  # noqa: ARG002
    ) -> ErrorReport:
        self.caller_identities.append(caller_identity)
        return ErrorReport(
            error_type="ValidateBundleError",
            message="bundle is invalid",
            title="Validate bundle error",
            type_uri="https://errors.pipelex.com/validate-bundle-error/",
            validation_errors=[ValidationErrorItem(category=ValidationErrorCategory.BLUEPRINT_VALIDATION, message="bad ref")],
        )


def _build_client(*, user_id: str | None) -> TestClient:
    app = FastAPI()

    if user_id is not None:
        authenticated_user = RequestUser(user_id=user_id)

        async def authenticate(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
            request.state.user = authenticated_user
            return await call_next(request)

        app.middleware("http")(authenticate)

    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


def _register_recording_validator(mocker: MockerFixture) -> _RecordingBundleValidator:
    config = ApiConfig(orchestration_mode=_MODE, allow_request_orchestration_mode_override=False)
    mocker.patch(f"{_PIPELINE_NS}.get_api_config", return_value=config)
    validator = _RecordingBundleValidator()
    mocker.patch(f"{_PIPELINE_NS}.get_bundle_validator_registry", return_value=BundleValidatorRegistry({_MODE: validator}))
    return validator


def _caller_of(mock_call: Any) -> CallerIdentity | None:
    caller_identity: CallerIdentity | None = mock_call.kwargs["caller_identity"]
    return caller_identity


class TestValidationCallerIdentity:
    def test_validate_hands_the_dispatched_validator_the_user_and_groups(self, mocker: MockerFixture) -> None:
        validator = _register_recording_validator(mocker)
        client = _build_client(user_id=_USER_ID)

        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS], "analytics_groups": _GROUPS})

        assert response.status_code == 200, response.text
        assert validator.caller_identities == [CallerIdentity(user_id=_USER_ID, extras=_GROUPS)]

    @pytest.mark.parametrize(
        "extras",
        [
            pytest.param({}, id="absent"),
            pytest.param({"analytics_groups": None}, id="null"),
            pytest.param({"analytics_groups": {}}, id="empty"),
        ],
    )
    def test_validate_without_groups_or_user_states_the_single_tenant_caller(self, mocker: MockerFixture, extras: dict[str, Any]) -> None:
        # No user on the request is a deployment with no user model, so the caller is the
        # single-tenant placeholder (which telemetry never attributes to a person), and no groups
        # means an empty mapping — nothing is invented.
        validator = _register_recording_validator(mocker)
        client = _build_client(user_id=None)

        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS], **extras})

        assert response.status_code == 200, response.text
        assert validator.caller_identities == [CallerIdentity(user_id=SINGLE_TENANT_USER_ID, extras={})]

    def test_validate_by_method_ref_hands_the_validator_the_caller(self, mocker: MockerFixture, install_method_package: Callable[..., Path]) -> None:
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        validator = _register_recording_validator(mocker)
        client = _build_client(user_id=_USER_ID)

        response = client.post("/v1/validate", json={"method_ref": _METHOD_REF, "analytics_groups": _GROUPS})

        assert response.status_code == 200, response.text
        assert validator.caller_identities == [CallerIdentity(user_id=_USER_ID, extras=_GROUPS)]

    def test_direct_validate_reaches_the_in_process_sweep_with_the_caller(self, mocker: MockerFixture) -> None:
        # The deployment default (`direct`) through the real in-process validator: the caller must
        # arrive at `validate_bundles_in_process`, which opens the caller scope for the whole sweep.
        sweep = mocker.patch(f"{_DIRECT_VALIDATOR_NS}.validate_bundles_in_process", wraps=validate_bundles_in_process)
        client = _build_client(user_id=_USER_ID)

        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS], "analytics_groups": _GROUPS})

        assert response.status_code == 200, response.text
        assert response.json()["is_valid"] is True
        assert sweep.call_count == 1
        assert _caller_of(sweep.call_args) == CallerIdentity(user_id=_USER_ID, extras=_GROUPS)

    @pytest.mark.parametrize("bad_groups", _BAD_GROUPS)
    def test_validate_refuses_malformed_groups_with_a_422_naming_the_field(self, mocker: MockerFixture, bad_groups: Any) -> None:
        validator = _register_recording_validator(mocker)
        client = _build_client(user_id=_USER_ID)

        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS], "analytics_groups": bad_groups})

        assert response.status_code == 422, response.text
        assert response.headers["content-type"] == "application/problem+json"
        body = response.json()
        assert body["error_type"] == "InvalidAnalyticsGroups"
        assert "analytics_groups" in body["detail"]
        assert validator.caller_identities == []

    def test_validate_failing_on_two_fields_gets_the_generic_error_type(self, mocker: MockerFixture) -> None:
        # Naming one field would send the caller to fix that one and leave the other for the next
        # request, so the classification falls back to the generic type and the detail names both.
        validator = _register_recording_validator(mocker)
        client = _build_client(user_id=_USER_ID)

        response = client.post(
            "/v1/validate",
            json={"mthds_contents": [VALID_MTHDS], "allow_signatures": "not-a-bool", "analytics_groups": {"Organization": "org_acme"}},
        )

        assert response.status_code == 422, response.text
        body = response.json()
        assert body["error_type"] == "ValidationError"
        assert "analytics_groups" in body["detail"]
        assert "allow_signatures" in body["detail"]
        assert validator.caller_identities == []

    def test_build_runner_sweeps_for_the_caller(self, mocker: MockerFixture) -> None:
        sweep = mocker.patch(f"{_RUNNER_NS}.validate_bundle", wraps=validate_bundle)
        client = _build_client(user_id=_USER_ID)

        response = client.post(
            "/v1/build/runner",
            json={"files": [{"content": VALID_MTHDS}], "pipe_ref": "smoke.echo", "analytics_groups": _GROUPS},
        )

        assert response.status_code == 200, response.text
        assert response.json()["is_valid"] is True
        assert sweep.call_count == 1
        assert _caller_of(sweep.call_args) == CallerIdentity(user_id=_USER_ID, extras=_GROUPS)

    def test_build_runner_without_groups_or_user_states_the_single_tenant_caller(self, mocker: MockerFixture) -> None:
        sweep = mocker.patch(f"{_RUNNER_NS}.validate_bundle", wraps=validate_bundle)
        client = _build_client(user_id=None)

        response = client.post("/v1/build/runner", json={"files": [{"content": VALID_MTHDS}], "pipe_ref": "smoke.echo"})

        assert response.status_code == 200, response.text
        assert _caller_of(sweep.call_args) == CallerIdentity(user_id=SINGLE_TENANT_USER_ID, extras={})

    @pytest.mark.parametrize("bad_groups", _BAD_GROUPS)
    def test_build_runner_refuses_malformed_groups_with_a_422_naming_the_field(self, mocker: MockerFixture, bad_groups: Any) -> None:
        sweep = mocker.patch(f"{_RUNNER_NS}.validate_bundle", wraps=validate_bundle)
        client = _build_client(user_id=_USER_ID)

        response = client.post(
            "/v1/build/runner",
            json={"files": [{"content": VALID_MTHDS}], "pipe_ref": "smoke.echo", "analytics_groups": bad_groups},
        )

        assert response.status_code == 422, response.text
        body = response.json()
        assert body["error_type"] == "InvalidAnalyticsGroups"
        assert "analytics_groups" in body["detail"]
        assert sweep.call_count == 0
