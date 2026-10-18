"""Envelope tests for `POST /v1/resolve` — the normalized-crate resolution route.

Pins `conformance/specs/pipelex-codegen.md#route-envelopes`, in the `conformance` repo beside the tests
that verify it: the request takes the method's tree as the protocol's `files` map XOR a `method_ref`,
read exactly as `/v1/validate` and the run routes read it; a produced verdict is a 200 discriminated on
`is_valid` with the crate on the valid arm; request-shape errors are 422 problem+json; an address-form
`method_ref` resolves the fetched package's tree, while the registry form is refused as a 422
`request.unsupported` until the method registry exists.
"""

import base64
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mthds.method_tree.digest import sha256_hex
from mthds.package.manifest.schema import MTHDS_STANDARD_VERSION
from pipelex.interpreter_hub import get_library_manager
from pytest_mock import MockerFixture

from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.limits import MAX_METHOD_TREE_FILE_BYTES
from pipelex_api.routes import router as api_router
from pipelex_api.routes.blob_upload import router as blob_upload_router
from tests.unit._constants import INVALID_MAIN_PIPE_MTHDS, SIBLING_MTHDS, VALID_MTHDS
from tests.unit._problems import assert_problem

RESOLVE_PATH = "/v1/resolve"


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    app.include_router(blob_upload_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


def _hash_entry(data: bytes) -> dict[str, Any]:
    return {"sha256": sha256_hex(data), "size": len(data)}


class TestResolveRoute:
    def test_a_tree_resolves_to_the_crate_on_the_valid_arm(self):
        client = _build_client()
        response = client.post(
            RESOLVE_PATH,
            json={"files": {"main.mthds": VALID_MTHDS, "steps/sibling.mthds": SIBLING_MTHDS, "README.md": "# Not a bundle\n"}},
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
        # Each bundle's tree path surfaces in the crate's provenance map.
        assert crate["source_map"]["smoke.echo"] == "main.mthds"
        assert crate["source_map"]["smoke.wrap_echo"] == "steps/sibling.mthds"

    def test_every_entry_form_reads_the_same_crate(self):
        # A bundle inline, in Base64 or by hash is the same file of the same tree, so the crate is the same.
        client = _build_client()
        data = VALID_MTHDS.encode("utf-8")
        missing = client.post("/v1/blobs/missing", json={"blobs": [_hash_entry(data)]})
        assert missing.status_code == 200, missing.text
        (blob,) = missing.json()["missing"]
        uploaded = client.request(blob["upload"]["method"], blob["upload"]["url"], content=data, headers=blob["upload"]["headers"])
        assert uploaded.status_code == 204, uploaded.text

        fingerprints: set[str] = set()
        for entry in (VALID_MTHDS, {"base64": base64.b64encode(data).decode("ascii")}, _hash_entry(data)):
            response = client.post(RESOLVE_PATH, json={"files": {"main.mthds": entry}})
            assert response.status_code == 200, response.text
            fingerprints.add(response.json()["crate"]["fingerprint"])
        assert len(fingerprints) == 1

    def test_an_invalid_tree_is_the_invalid_arm_named_by_tree_path(self):
        client = _build_client()
        response = client.post(RESOLVE_PATH, json={"files": {"methods/broken.mthds": INVALID_MAIN_PIPE_MTHDS}})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        assert body["errors"], "an invalid verdict must carry a non-empty errors[]"
        assert body["errors"][0]["code"]
        assert body["errors"][0]["detail"]
        # The bundle's tree path threads through to the items' location.
        assert body["errors"][0]["location"]["file"] == "methods/broken.mthds"
        # No crate exists on the invalid arm; the runnability facts are /validate vocabulary, absent here.
        assert "crate" not in body
        assert "is_runnable" not in body

    def test_address_method_ref_resolves_the_fetched_package(self, install_method_package: Callable[..., Path]):
        # An address-form ref resolves through the same fetch path as a `method_ref` run, and the
        # package's bundles keep their tree paths as sources.
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        client = _build_client()
        response = client.post(RESOLVE_PATH, json={"method_ref": "github.com/pipelex/methods/documents@v0.1.0"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        crate = body["crate"]
        assert "smoke.echo" in crate["pipes"]
        assert crate["source_map"]["smoke.echo"] == "documents.mthds"

    def test_registry_form_method_ref_is_an_unsupported_request(self):
        # The registry form (any non-address reference) stays reserved for the packaging
        # program's closing phase — an honest refusal of the form, never a silent empty verdict.
        client = _build_client()
        response = client.post(RESOLVE_PATH, json={"method_ref": "acme/invoice-tools"})
        problem = assert_problem(response, status=422, code="request.unsupported")
        assert problem["params"] == {"field": "method_ref", "reason": "registry_form_method_ref"}

    @pytest.mark.parametrize(
        ("payload", "field"),
        [
            pytest.param({}, "files", id="neither"),
            pytest.param({"files": {"main.mthds": VALID_MTHDS}, "method_ref": "acme/x"}, "method_ref", id="both"),
            pytest.param({"method_ref": "acme/x", "dependencies": {}}, "dependencies", id="dependencies-without-files"),
        ],
    )
    def test_a_malformed_method_selector_is_a_request_shape_422(self, payload: dict[str, Any], field: str):
        # The model's rule names the field to change, never the body as a whole: the first selector when none is sent,
        # the second when both are, and the `dependencies` sent without the tree they belong to.
        assert_problem(_build_client().post(RESOLVE_PATH, json=payload), status=422, code="request.invalid", field=field)

    @pytest.mark.parametrize(
        ("files", "code", "reason"),
        [
            pytest.param([{"content": VALID_MTHDS, "source": "main.mthds"}], "request.invalid", None, id="the-retired-list-shape"),
            pytest.param({}, "method.package_invalid", "empty_tree", id="empty-map"),
            pytest.param({"../main.mthds": VALID_MTHDS}, "security.input_path_refused", None, id="path-leaving-the-tree"),
            pytest.param({".mthds/main.mthds": VALID_MTHDS}, "method.package_invalid", "excluded_name", id="excluded-name"),
        ],
    )
    def test_a_files_member_that_is_no_method_tree_is_refused_as_validate_refuses_it(self, files: Any, code: str, reason: str | None):
        client = _build_client()
        response = client.post(RESOLVE_PATH, json={"files": files})
        validate_response = client.post("/v1/validate", json={"files": files})
        problem = assert_problem(response, status=422, code=code)
        validate_problem = assert_problem(validate_response, status=422, code=code)
        if reason is not None:
            assert problem["params"]["reason"] == reason, problem
        assert problem.get("params") == validate_problem.get("params")

    def test_a_hash_the_runner_does_not_hold_is_a_422_naming_it(self):
        notes = b"notes the runner never received"
        response = _build_client().post(RESOLVE_PATH, json={"files": {"main.mthds": VALID_MTHDS, "notes.txt": _hash_entry(notes)}})
        problem = assert_problem(response, status=422, code="request.blobs_missing")
        assert problem["params"] == {"missing_blobs": [sha256_hex(notes)]}

    def test_a_file_past_the_tree_limit_is_refused(self):
        response = _build_client().post(RESOLVE_PATH, json={"files": {"main.mthds": VALID_MTHDS, "big.txt": "a" * (MAX_METHOD_TREE_FILE_BYTES + 1)}})
        problem = assert_problem(response, status=422, code="method.package_invalid")
        assert problem["params"] == {"reason": "file_too_large", "path": "big.txt", "limit": MAX_METHOD_TREE_FILE_BYTES}

    def test_python_in_a_tree_is_refused_where_it_could_not_run(self):
        response = _build_client().post(RESOLVE_PATH, json={"files": {"main.mthds": VALID_MTHDS, "helpers/tool.py": "VALUE = 1\n"}})
        assert_problem(response, status=501, code="pipelex.deployment.custom_code_requires_sandbox")

    def test_a_tree_without_a_bundle_is_refused(self):
        response = _build_client().post(RESOLVE_PATH, json={"files": {"notes.txt": "no bundle here"}})
        problem = assert_problem(response, status=422, code="method.package_invalid")
        assert problem["params"] == {"reason": "no_bundle"}

    def test_resolve_tears_down_its_library(self, mocker: MockerFixture):
        # The engine core leaves the library loaded + current on success (so /codegen can read live
        # pipes); the route owns teardown. Conservation property: opens == teardowns.
        library_manager = get_library_manager()
        open_spy = mocker.spy(library_manager, "open_library")
        teardown_spy = mocker.spy(library_manager, "teardown")

        client = _build_client()
        response = client.post(RESOLVE_PATH, json={"files": {"main.mthds": VALID_MTHDS}})

        assert response.status_code == 200, response.text
        assert open_spy.call_count >= 1
        assert open_spy.call_count == teardown_spy.call_count
