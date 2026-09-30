"""`default_pipe_ref` on the /validate valid arm — the pipe a selector-less run would execute.

The canonical `PipelexValidationReport` is manifest-blind: its `bundle_blueprint` is the batch's
primary blueprint, so a package whose `METHODS.toml` names an entry pipe the closure would not
default to validates with a report from which a consumer can only derive the WRONG entry pipe, or
none. These tests pin the route's own field, which applies the run routes' precedence — the fetched
manifest's `main_pipe`, else the closure's primary blueprint — so a by-address consumer projects a
signature for the pipe `/execute` actually defaults to.
"""

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.exception_handlers import register_exception_handlers
from api.routes import router as api_router
from tests.unit._constants import (
    COLLIDING_ECHO_LIST_MTHDS,
    INVALID_MAIN_PIPE_MTHDS,
    NO_MAIN_PIPE_MTHDS,
    SECOND_MAIN_PIPE_MTHDS,
    STUB_METHOD_ADDRESS,
    STUB_METHOD_MANIFEST_MAIN_PIPE_SHOUT,
    STUB_METHOD_MANIFEST_NO_MAIN_PIPE,
    VALID_MTHDS,
)

_METHOD_REF = f"{STUB_METHOD_ADDRESS}@v0.1.0"


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


class TestValidateDefaultPipeRef:
    def test_inline_contents_report_the_closures_declaration_qualified(self):
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        # The bundle declares `main_pipe = "echo"` in domain `smoke`; the field qualifies it, where
        # `bundle_blueprint.main_pipe` leaves the caller to reconstruct the domain.
        assert body["default_pipe_ref"] == "smoke.echo"

    def test_a_closure_declaring_no_main_pipe_reports_null(self):
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [NO_MAIN_PIPE_MTHDS]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        assert body["default_pipe_ref"] is None

    def test_several_declared_main_pipes_report_the_run_default_not_null(self):
        # The field states the RUN default (`select_primary_blueprint`: first blueprint declaring
        # `main_pipe`), NOT the build routes' stricter rule that 422s on several. `/execute` and
        # `/start` run this closure happily, so reporting null would make a consumer refuse to
        # prepare a method the server would run.
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS, SECOND_MAIN_PIPE_MTHDS]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        assert body["default_pipe_ref"] == "smoke.echo"

    def test_the_invalid_arm_carries_no_default_pipe_ref(self):
        # No library was assembled, so there is no entry pipe to name — the field follows the other
        # structural artifacts into absence rather than riding as a null.
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [INVALID_MAIN_PIPE_MTHDS]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        assert "default_pipe_ref" not in body

    def test_method_ref_reports_the_manifests_entry_pipe_over_the_closures(self, install_method_package: Callable[..., Path]):
        # The gap this field closes: the manifest names `shout`, the closure's own primary blueprint
        # declares `echo`. A run by this address executes `other.shout`; a consumer reading
        # `bundle_blueprint.main_pipe` would project `echo` and type a call site nothing runs.
        # The package's files are read in sorted order, so `a_smoke.mthds` is the batch's primary
        # blueprint — the one whose `main_pipe` the canonical report reports.
        install_method_package(
            files={"a_smoke.mthds": VALID_MTHDS, "b_other.mthds": SECOND_MAIN_PIPE_MTHDS},
            manifest_toml=STUB_METHOD_MANIFEST_MAIN_PIPE_SHOUT,
        )
        client = _build_client()
        response = client.post("/v1/validate", json={"method_ref": _METHOD_REF})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        assert body["default_pipe_ref"] == "other.shout"
        # The report itself stays manifest-blind — which is exactly why the field has to exist.
        assert body["bundle_blueprint"]["main_pipe"] == "echo"

    def test_method_ref_qualifies_the_manifests_bare_code(self, install_method_package: Callable[..., Path]):
        # A `METHODS.toml` `main_pipe` is a bare code; the wire field is always qualified.
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        client = _build_client()
        response = client.post("/v1/validate", json={"method_ref": _METHOD_REF})
        assert response.status_code == 200, response.text
        assert response.json()["default_pipe_ref"] == "smoke.echo"

    def test_a_manifest_without_main_pipe_falls_back_to_the_closures_declaration(self, install_method_package: Callable[..., Path]):
        install_method_package(files={"documents.mthds": VALID_MTHDS}, manifest_toml=STUB_METHOD_MANIFEST_NO_MAIN_PIPE)
        client = _build_client()
        response = client.post("/v1/validate", json={"method_ref": _METHOD_REF})
        assert response.status_code == 200, response.text
        assert response.json()["default_pipe_ref"] == "smoke.echo"

    def test_a_manifest_naming_a_pipe_the_closure_lacks_reports_null(self, install_method_package: Callable[..., Path]):
        # The manifest names `shout`; the package's closure holds only `smoke.echo`. A selector-less
        # run would pass `shout` and fail to resolve it, so the field must not fall back to the
        # closure's `echo` — that names a pipe no run of this address executes.
        install_method_package(files={"smoke.mthds": VALID_MTHDS}, manifest_toml=STUB_METHOD_MANIFEST_MAIN_PIPE_SHOUT)
        client = _build_client()
        response = client.post("/v1/validate", json={"method_ref": _METHOD_REF})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        assert body["default_pipe_ref"] is None

    def test_an_ambiguous_manifest_bare_code_reports_null(self, install_method_package: Callable[..., Path]):
        # The manifest names `echo`, declared by both `smoke` and `twin`. The engine's entry lookup
        # raises on an ambiguous bare code rather than picking a winner, so the field says nothing.
        install_method_package(files={"smoke.mthds": VALID_MTHDS, "twin.mthds": COLLIDING_ECHO_LIST_MTHDS})
        client = _build_client()
        response = client.post("/v1/validate", json={"method_ref": _METHOD_REF})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        assert body["default_pipe_ref"] is None
