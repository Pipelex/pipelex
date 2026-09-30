"""Envelope tests for `POST /v1/resolve` — the normalized-crate resolution route.

Pins `docs/specs/pipelex-codegen.md#route-envelopes` (workspace root): the request accepts inline
`files[]` XOR a `method_ref`; a produced verdict is a 200 discriminated on `is_valid` with the
crate on the valid arm; request-shape errors are 422 problem+json; an address-form `method_ref`
resolves the fetched package's `.mthds` files into the closure, while the registry form keeps its
honest 501 until the method registry exists.
"""

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from mthds.package.manifest.schema import MTHDS_STANDARD_VERSION
from pipelex.interpreter_hub import get_library_manager
from pytest_mock import MockerFixture

from api.exception_handlers import register_exception_handlers
from api.routes import router as api_router
from tests.unit._constants import INVALID_MAIN_PIPE_MTHDS, SIBLING_MTHDS, VALID_MTHDS


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


class TestResolveRoute:
    def test_valid_files_return_200_crate_on_valid_arm(self):
        client = _build_client()
        response = client.post(
            "/v1/resolve",
            json={"files": [{"content": VALID_MTHDS, "source": "main.mthds"}, {"content": SIBLING_MTHDS, "source": "sibling.mthds"}]},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        crate = body["crate"]
        # The canonical crate encoding: qualified refs, materialized natives, fingerprint + version.
        assert crate["fingerprint"]
        assert crate["mthds_version"] == MTHDS_STANDARD_VERSION
        assert "smoke.echo" in crate["pipes"]
        assert "smoke.wrap_echo" in crate["pipes"]
        assert "native.Text" in crate["concepts"], "referenced natives must be materialized into the crate"
        # Sources threaded per file[] entry surface in the crate's provenance map.
        assert crate["source_map"]["smoke.echo"] == "main.mthds"
        assert crate["source_map"]["smoke.wrap_echo"] == "sibling.mthds"

    def test_invalid_files_return_200_invalid_arm_with_structured_errors(self):
        client = _build_client()
        response = client.post("/v1/resolve", json={"files": [{"content": INVALID_MAIN_PIPE_MTHDS, "source": "broken.mthds"}]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        assert body["validation_errors"], "an invalid verdict must carry a non-empty validation_errors[]"
        assert body["validation_errors"][0]["message"]
        # The per-file source threads through to the diagnostics.
        assert body["validation_errors"][0]["source"] == "broken.mthds"
        # No crate exists on the invalid arm; the runnability facts are /validate vocabulary, absent here.
        assert "crate" not in body
        assert "is_runnable" not in body

    def test_address_method_ref_resolves_the_fetched_package(self, install_method_package: Callable[..., Path]):
        # The address-form un-reserve (run-by-address MVP Phase 2): a `github.com/...` ref
        # resolves through the same fetch path as a `method_ref` run, and the package's
        # `.mthds` files feed the closure with their real relative paths as sources.
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        client = _build_client()
        response = client.post("/v1/resolve", json={"method_ref": "github.com/pipelex/methods/documents@v0.1.0"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        crate = body["crate"]
        assert "smoke.echo" in crate["pipes"]
        # The package's real file name rides the crate's provenance map.
        assert crate["source_map"]["smoke.echo"] == "documents.mthds"

    def test_registry_form_method_ref_keeps_the_501(self):
        # The registry form (any non-address reference) stays reserved for the packaging
        # program's closing phase — an honest 501, never a silent empty verdict.
        client = _build_client()
        response = client.post("/v1/resolve", json={"method_ref": "acme/invoice-tools"})
        assert response.status_code == 501, response.text
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "MethodRefNotSupported"

    def test_neither_or_both_selectors_is_422_problem_json(self):
        client = _build_client()
        neither = client.post("/v1/resolve", json={})
        both = client.post("/v1/resolve", json={"files": [{"content": VALID_MTHDS}], "method_ref": "acme/x"})
        for response in (neither, both):
            assert response.status_code == 422, response.text
            assert response.headers["content-type"] == "application/problem+json"
            assert response.json()["error_type"] == "ValidationError"

    def test_oversized_file_is_422_problem_json(self):
        client = _build_client()
        response = client.post("/v1/resolve", json={"files": [{"content": "a" * (2 * 1024 * 1024)}]})
        assert response.status_code == 422, response.text
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "ValidationError"

    def test_resolve_tears_down_its_library(self, mocker: MockerFixture):
        # The engine core leaves the library loaded + current on success (so /codegen can read live
        # pipes); the route owns teardown. Conservation property: opens == teardowns.
        library_manager = get_library_manager()
        open_spy = mocker.spy(library_manager, "open_library")
        teardown_spy = mocker.spy(library_manager, "teardown")

        client = _build_client()
        response = client.post("/v1/resolve", json={"files": [{"content": VALID_MTHDS}]})

        assert response.status_code == 200, response.text
        assert open_spy.call_count >= 1
        assert open_spy.call_count == teardown_spy.call_count
