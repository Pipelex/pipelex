"""`/validate` hands its validator the read scope its request names, and nothing else.

A validator that dispatches the validation to another process hands the method's trees to its worker
through a blob store, and the scope of that store must be the trusted one the host named for the request,
the organization on a multi-tenant host, as a run's worker reads under the run's read scope. Every
failure here is silent by construction: a keyword left out of `ApiRunner(...)` or `validate_bundles(...)`
still answers 200, and only the worker finds no tree. So these tests read the scope off the call a
recording validator receives, on each arm of the request, and check that a `files` tree is already held
under the scope when the validator is called, so it can name the tree by digest.

A request without a `read_scope` hands the validator none, even on a deployment that identifies its
callers, where a run would fall back to the caller's id: nothing lists or erases what a validation would
leave under that prefix.
"""

import base64
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from mthds.method_tree.digest import digest_of_contents
from mthds.protocol.problem.registry import CoreCode
from pipelex.base_exceptions import ErrorReport, ValidationErrorCategory, ValidationErrorItem
from pipelex.plugins.bundle_validator_registry import BundleValidatorRegistry
from pipelex.system.caller_identity import CallerIdentity
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pytest_mock import MockerFixture

from pipelex_api.api_config import ApiConfig
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router
from pipelex_api.security import RequestUser
from tests.unit._constants import STUB_METHOD_ADDRESS, VALID_MTHDS

_PIPELINE_NS = "pipelex_api.routes.pipelex.pipeline"
_MODE = "temporal"
_USER_ID = "user_42"
_READ_SCOPE = "org-a"
_METHOD_REF = f"{STUB_METHOD_ADDRESS}@v0.1.0"
_TEMPLATE = b"<h1>{{ text }}</h1>"
_TEMPLATE_B64 = base64.b64encode(_TEMPLATE).decode("ascii")


class _RecordingBundleValidator:
    """Records the read scope of every validation dispatched to it, and what the blob store held then."""

    def __init__(self, *, blob_storage: InMemoryStorageProvider) -> None:
        self._blob_storage = blob_storage
        self.read_scopes: list[str | None] = []
        self.held_keys: list[set[str]] = []

    async def validate_bundles(
        self,
        *,
        mthds_contents: list[str] | None,  # noqa: ARG002
        mthds_sources: list[str] | None,  # noqa: ARG002
        allow_signatures: bool,  # noqa: ARG002
        library_dirs: Sequence[Path] | None,  # noqa: ARG002
        caller_identity: CallerIdentity | None,  # noqa: ARG002
        graph_pipe_code: str | None,  # noqa: ARG002
        submitted_files: Mapping[str, bytes] | None,  # noqa: ARG002
        method_dir: Path | None,  # noqa: ARG002
        methods_dirs: Sequence[Path] | None,  # noqa: ARG002
        read_scope: str | None,
    ) -> ErrorReport:
        self.read_scopes.append(read_scope)
        self.held_keys.append(set(self._blob_storage.root))
        return ErrorReport.make_for_code(
            code=CoreCode.METHOD_INVALID,
            error_type="ValidateBundleError",
            message="bundle is invalid",
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


def _register_recording_validator(mocker: MockerFixture, *, blob_storage: InMemoryStorageProvider) -> _RecordingBundleValidator:
    config = ApiConfig(orchestration_mode=_MODE, allow_request_orchestration_mode_override=False)
    mocker.patch(f"{_PIPELINE_NS}.get_api_config", return_value=config)
    validator = _RecordingBundleValidator(blob_storage=blob_storage)
    mocker.patch(f"{_PIPELINE_NS}.get_bundle_validator_registry", return_value=BundleValidatorRegistry({_MODE: validator}))
    return validator


_REQUEST_METHODS = [
    pytest.param({"mthds_contents": [VALID_MTHDS]}, id="mthds_contents"),
    pytest.param({"mthds_contents": [VALID_MTHDS], "resources": {"templates/page.html": _TEMPLATE_B64}}, id="mthds_contents-with-resources"),
    pytest.param({"files": {"main.mthds": VALID_MTHDS}}, id="files"),
    pytest.param({"method_ref": _METHOD_REF}, id="method_ref"),
]


class TestValidateReadScope:
    @pytest.mark.parametrize("request_method", _REQUEST_METHODS)
    def test_the_validator_receives_the_read_scope_the_request_names(
        self,
        mocker: MockerFixture,
        blob_storage: InMemoryStorageProvider,
        install_method_package: Callable[..., Path],
        request_method: dict[str, Any],
    ) -> None:
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        validator = _register_recording_validator(mocker, blob_storage=blob_storage)
        client = _build_client(user_id=_USER_ID)

        response = client.post("/v1/validate", json={**request_method, "read_scope": _READ_SCOPE})

        assert response.status_code == 200, response.text
        assert response.json()["is_valid"] is False
        assert validator.read_scopes == [_READ_SCOPE]

    @pytest.mark.parametrize("user_id", [pytest.param(_USER_ID, id="identified-caller"), pytest.param(None, id="single-tenant")])
    @pytest.mark.parametrize("request_method", _REQUEST_METHODS)
    def test_a_request_without_a_read_scope_hands_the_validator_none_never_the_callers_id(
        self,
        mocker: MockerFixture,
        blob_storage: InMemoryStorageProvider,
        install_method_package: Callable[..., Path],
        request_method: dict[str, Any],
        user_id: str | None,
    ) -> None:
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        validator = _register_recording_validator(mocker, blob_storage=blob_storage)
        client = _build_client(user_id=user_id)

        response = client.post("/v1/validate", json=request_method)

        assert response.status_code == 200, response.text
        assert validator.read_scopes == [None]
        assert validator.held_keys == [set()]

    def test_a_files_tree_is_held_under_the_read_scope_before_the_validator_is_called(
        self, mocker: MockerFixture, blob_storage: InMemoryStorageProvider
    ) -> None:
        """A dispatched validator names the tree by its digest, so the tree must already be in the scope's blob store."""
        validator = _register_recording_validator(mocker, blob_storage=blob_storage)
        client = _build_client(user_id=_USER_ID)
        contents = {"main.mthds": VALID_MTHDS.encode("utf-8"), "templates/page.html": _TEMPLATE}

        response = client.post(
            "/v1/validate",
            json={"files": {"main.mthds": VALID_MTHDS, "templates/page.html": {"base64": _TEMPLATE_B64}}, "read_scope": _READ_SCOPE},
        )

        assert response.status_code == 200, response.text
        digest_hex = digest_of_contents(contents).removeprefix("sha256:")
        (held_keys,) = validator.held_keys
        assert f"{_READ_SCOPE}/trees/{digest_hex}" in held_keys
        assert all(key.startswith(f"{_READ_SCOPE}/") for key in held_keys)
