"""`/validate` hands its validator the id of the request it serves, on every arm of the request.

A validator that dispatches the validation to a worker runs it in another process, which the request-id
middleware's in-process binding does not reach, so the id must travel with the dispatch, as a run's travels
on its metadata. Leaving it out fails silently: the route still answers 200, and only the worker's log lines
lose the id. So these tests read the id off the call a recording validator receives, with the app wrapped in
`RequestIdMiddleware` the way `pipelex_api.main` wraps it: an inbound `X-Request-ID` is the id handed over,
and without one the validator receives the id the middleware minted and echoed.
"""

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mthds.protocol.problem.registry import CoreCode
from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.errors.bundle_validation_failure import BundleValidationFailure
from pipelex.errors.problem import ProblemView, make_problem
from pipelex.plugins.bundle_validator_registry import BundleValidatorRegistry
from pipelex.system.caller_identity import CallerIdentity
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pytest_mock import MockerFixture

from pipelex_api.api_config import ApiConfig
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.middleware import REQUEST_ID_HEADER, RequestIdMiddleware
from pipelex_api.routes import router as api_router
from tests.unit._constants import STUB_METHOD_ADDRESS, VALID_MTHDS

_PIPELINE_NS = "pipelex_api.routes.pipelex.pipeline"
_MODE = "temporal"
_INBOUND_REQUEST_ID = "01HNJZ4XR7K3Q9D8MWAQ7FY2E5"
_METHOD_REF = f"{STUB_METHOD_ADDRESS}@v0.1.0"


class _RecordingBundleValidator:
    """Records the request id of every validation dispatched to it, and answers an invalid verdict."""

    def __init__(self) -> None:
        self.request_ids: list[str | None] = []

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
        read_scope: str | None,  # noqa: ARG002
        request_id: str | None,
    ) -> BundleValidationFailure:
        self.request_ids.append(request_id)
        return BundleValidationFailure(
            problem=make_problem(code=CoreCode.METHOD_INVALID, view=ProblemView.OPERATOR),
            validation_errors=[ValidationErrorItem(category=ValidationErrorCategory.BLUEPRINT_VALIDATION, message="bad ref")],
        )


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(RequestIdMiddleware(app))


def _register_recording_validator(mocker: MockerFixture) -> _RecordingBundleValidator:
    config = ApiConfig(orchestration_mode=_MODE, allow_request_orchestration_mode_override=False)
    mocker.patch(f"{_PIPELINE_NS}.get_api_config", return_value=config)
    validator = _RecordingBundleValidator()
    mocker.patch(f"{_PIPELINE_NS}.get_bundle_validator_registry", return_value=BundleValidatorRegistry({_MODE: validator}))
    return validator


_REQUEST_METHODS = [
    pytest.param({"mthds_contents": [VALID_MTHDS]}, id="mthds_contents"),
    pytest.param({"files": {"main.mthds": VALID_MTHDS}}, id="files"),
    pytest.param({"method_ref": _METHOD_REF}, id="method_ref"),
]


class TestValidateRequestId:
    @pytest.mark.parametrize("request_method", _REQUEST_METHODS)
    def test_the_validator_receives_the_inbound_request_id(
        self,
        mocker: MockerFixture,
        blob_storage: InMemoryStorageProvider,  # noqa: ARG002
        install_method_package: Callable[..., Path],
        request_method: dict[str, Any],
    ) -> None:
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        validator = _register_recording_validator(mocker)
        client = _build_client()

        response = client.post("/v1/validate", json=request_method, headers={REQUEST_ID_HEADER: _INBOUND_REQUEST_ID})

        assert response.status_code == 200, response.text
        assert response.json()["is_valid"] is False
        assert response.headers[REQUEST_ID_HEADER] == _INBOUND_REQUEST_ID
        assert validator.request_ids == [_INBOUND_REQUEST_ID]

    @pytest.mark.parametrize("request_method", _REQUEST_METHODS)
    def test_the_validator_receives_the_minted_request_id(
        self,
        mocker: MockerFixture,
        blob_storage: InMemoryStorageProvider,  # noqa: ARG002
        install_method_package: Callable[..., Path],
        request_method: dict[str, Any],
    ) -> None:
        """Without an inbound header the middleware mints an id, and the validator receives the one the caller was answered under."""
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        validator = _register_recording_validator(mocker)
        client = _build_client()

        response = client.post("/v1/validate", json=request_method)

        assert response.status_code == 200, response.text
        minted_request_id = response.headers[REQUEST_ID_HEADER]
        assert minted_request_id
        assert validator.request_ids == [minted_request_id]
