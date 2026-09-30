"""The /validate graph is drawn from the pipe a selector-less run of the request would execute.

The runtime's graph arm defaults to the primary blueprint's `main_pipe`, which is manifest-blind:
a fetched package whose `METHODS.toml` names the entry pipe would be graphed from another pipe, or
not at all when its bundles declare no `main_pipe` of their own. The route hands the runtime the
manifest's `main_pipe` as the graph target, so `graph_spec` and `default_pipe_ref` name the same
pipe. These tests read the target twice: off the graph the real in-process validator draws, and
off the call a dispatched validator receives.
"""

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipelex.base_exceptions import ErrorReport, ValidationErrorCategory, ValidationErrorItem
from pipelex.plugins.bundle_validator_registry import BundleValidatorRegistry
from pipelex.system.caller_identity import CallerIdentity
from pytest_mock import MockerFixture

from api.api_config import ApiConfig
from api.exception_handlers import register_exception_handlers
from api.routes import router as api_router
from tests.unit._constants import (
    NO_MAIN_PIPE_MTHDS,
    SECOND_MAIN_PIPE_MTHDS,
    STUB_METHOD_ADDRESS,
    STUB_METHOD_MANIFEST_MAIN_PIPE_SHOUT,
    STUB_METHOD_MANIFEST_NO_MAIN_PIPE,
    STUB_METHOD_MANIFEST_NOMAIN_ENTRY,
    VALID_MTHDS,
)

_PIPELINE_NS = "api.routes.pipelex.pipeline"
_MODE = "temporal"
_METHOD_REF = f"{STUB_METHOD_ADDRESS}@v0.1.0"


class _RecordingBundleValidator:
    """Records the graph target of every validation dispatched to it, then answers an invalid verdict."""

    def __init__(self) -> None:
        self.graph_pipe_codes: list[str | None] = []

    async def validate_bundles(
        self,
        *,
        mthds_contents: list[str],  # noqa: ARG002
        mthds_sources: list[str] | None,  # noqa: ARG002
        allow_signatures: bool,  # noqa: ARG002
        library_dirs: Sequence[Path] | None,  # noqa: ARG002
        caller_identity: CallerIdentity | None,  # noqa: ARG002
        graph_pipe_code: str | None,
    ) -> ErrorReport:
        self.graph_pipe_codes.append(graph_pipe_code)
        return ErrorReport(
            error_type="ValidateBundleError",
            message="bundle is invalid",
            title="Validate bundle error",
            type_uri="https://errors.pipelex.com/validate-bundle-error/",
            validation_errors=[ValidationErrorItem(category=ValidationErrorCategory.BLUEPRINT_VALIDATION, message="bad ref")],
        )


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


def _register_recording_validator(mocker: MockerFixture) -> _RecordingBundleValidator:
    config = ApiConfig(orchestration_mode=_MODE, allow_request_orchestration_mode_override=False)
    mocker.patch(f"{_PIPELINE_NS}.get_api_config", return_value=config)
    validator = _RecordingBundleValidator()
    mocker.patch(f"{_PIPELINE_NS}.get_bundle_validator_registry", return_value=BundleValidatorRegistry({_MODE: validator}))
    return validator


def _graphed_pipe_ref(body: dict[str, Any]) -> str:
    """The qualified ref of the pipe the valid arm's `graph_spec` was drawn from."""
    pipeline_ref: dict[str, str] = body["graph_spec"]["pipeline_ref"]
    return f"{pipeline_ref['domain']}.{pipeline_ref['main_pipe']}"


class TestValidateGraphTarget:
    def test_a_package_whose_manifest_alone_names_the_entry_pipe_is_graphed(self, install_method_package: Callable[..., Path]) -> None:
        # The bundle declares no `main_pipe`, so the runtime's default target is nothing and the
        # graph used to be null although `default_pipe_ref` named the manifest's pipe.
        install_method_package(files={"documents.mthds": NO_MAIN_PIPE_MTHDS}, manifest_toml=STUB_METHOD_MANIFEST_NOMAIN_ENTRY)
        client = _build_client()

        response = client.post("/v1/validate", json={"method_ref": _METHOD_REF})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        assert body["bundle_blueprint"]["main_pipe"] is None
        assert body["default_pipe_ref"] == "nomain.echo"
        assert _graphed_pipe_ref(body) == "nomain.echo"

    def test_the_manifests_entry_pipe_is_graphed_over_the_closures(self, install_method_package: Callable[..., Path]) -> None:
        # The manifest names `shout`; the primary blueprint (`a_smoke.mthds`, read first) declares
        # `echo`. A run by this address executes `other.shout`, so that is the pipe to draw.
        install_method_package(
            files={"a_smoke.mthds": VALID_MTHDS, "b_other.mthds": SECOND_MAIN_PIPE_MTHDS},
            manifest_toml=STUB_METHOD_MANIFEST_MAIN_PIPE_SHOUT,
        )
        client = _build_client()

        response = client.post("/v1/validate", json={"method_ref": _METHOD_REF})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["bundle_blueprint"]["main_pipe"] == "echo"
        assert body["default_pipe_ref"] == "other.shout"
        assert _graphed_pipe_ref(body) == "other.shout"

    def test_a_manifest_without_main_pipe_graphs_the_closures_declaration(self, install_method_package: Callable[..., Path]) -> None:
        install_method_package(files={"documents.mthds": VALID_MTHDS}, manifest_toml=STUB_METHOD_MANIFEST_NO_MAIN_PIPE)
        client = _build_client()

        response = client.post("/v1/validate", json={"method_ref": _METHOD_REF})

        assert response.status_code == 200, response.text
        assert _graphed_pipe_ref(response.json()) == "smoke.echo"

    def test_a_manifest_naming_a_pipe_the_closure_lacks_gets_no_graph(self, install_method_package: Callable[..., Path]) -> None:
        # The manifest names `shout`; the closure holds only `smoke.echo`. No run by this address
        # executes `echo`, so drawing it would disagree with `default_pipe_ref`; the unresolved
        # target degrades the graph and leaves the verdict valid.
        install_method_package(files={"smoke.mthds": VALID_MTHDS}, manifest_toml=STUB_METHOD_MANIFEST_MAIN_PIPE_SHOUT)
        client = _build_client()

        response = client.post("/v1/validate", json={"method_ref": _METHOD_REF})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        assert body["default_pipe_ref"] is None
        assert body["graph_spec"] is None

    def test_inline_contents_graph_the_closures_declaration(self) -> None:
        client = _build_client()

        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS]})

        assert response.status_code == 200, response.text
        assert _graphed_pipe_ref(response.json()) == "smoke.echo"

    def test_the_dispatched_validator_receives_the_manifests_bare_code(
        self, mocker: MockerFixture, install_method_package: Callable[..., Path]
    ) -> None:
        # A worker-dispatched validator draws its graph on the worker, so the target must travel
        # through the seam; it is the manifest's bare code, resolved there as a run resolves it.
        install_method_package(files={"documents.mthds": NO_MAIN_PIPE_MTHDS}, manifest_toml=STUB_METHOD_MANIFEST_NOMAIN_ENTRY)
        validator = _register_recording_validator(mocker)
        client = _build_client()

        response = client.post("/v1/validate", json={"method_ref": _METHOD_REF})

        assert response.status_code == 200, response.text
        assert validator.graph_pipe_codes == ["echo"]

    def test_the_dispatched_validator_keeps_its_default_target_for_inline_contents(self, mocker: MockerFixture) -> None:
        validator = _register_recording_validator(mocker)
        client = _build_client()

        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS]})

        assert response.status_code == 200, response.text
        assert validator.graph_pipe_codes == [None]
