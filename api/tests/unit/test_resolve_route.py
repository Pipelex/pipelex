"""Envelope tests for `POST /v1/resolve` — the normalized-crate resolution route.

Pins `conformance/specs/pipelex-codegen.md#route-envelopes`, in the `conformance` repo beside the tests
that verify it: the request takes the method's tree as the protocol's `files` map XOR a `method_ref`,
read exactly as `/v1/validate` and the run routes read it; a produced verdict is a 200 discriminated on
`is_valid` with the crate on the valid arm; request-shape errors are 422 problem+json; an address-form
`method_ref` resolves the fetched package's tree, while the registry form keeps its honest 501 until the
method registry exists.
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

RESOLVE_PATH = "/v1/resolve"


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    app.include_router(blob_upload_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


def _hash_entry(data: bytes) -> dict[str, Any]:
    return {"sha256": sha256_hex(data), "size": len(data)}


def _assert_problem(response: Any, *, status: int, error_type: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    problem: dict[str, Any] = response.json()
    assert problem["error_type"] == error_type, response.text
    assert "is_valid" not in problem
    return problem


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
        assert body["validation_errors"], "an invalid verdict must carry a non-empty validation_errors[]"
        assert body["validation_errors"][0]["message"]
        # The bundle's tree path threads through to the diagnostics.
        assert body["validation_errors"][0]["source"] == "methods/broken.mthds"
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

    def test_registry_form_method_ref_keeps_the_501(self):
        # The registry form (any non-address reference) stays reserved for the packaging
        # program's closing phase — an honest 501, never a silent empty verdict.
        client = _build_client()
        response = client.post(RESOLVE_PATH, json={"method_ref": "acme/invoice-tools"})
        _assert_problem(response, status=501, error_type="MethodRefNotSupported")

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({}, id="neither"),
            pytest.param({"files": {"main.mthds": VALID_MTHDS}, "method_ref": "acme/x"}, id="both"),
            pytest.param({"method_ref": "acme/x", "dependencies": {}}, id="dependencies-without-files"),
        ],
    )
    def test_a_malformed_method_selector_is_a_request_shape_422(self, payload: dict[str, Any]):
        _assert_problem(_build_client().post(RESOLVE_PATH, json=payload), status=422, error_type="ValidationError")

    @pytest.mark.parametrize(
        ("files", "refusal_code"),
        [
            pytest.param([{"content": VALID_MTHDS, "source": "main.mthds"}], None, id="the-retired-list-shape"),
            pytest.param({}, "empty_tree", id="empty-map"),
            pytest.param({"../main.mthds": VALID_MTHDS}, "invalid_tree_path", id="path-leaving-the-tree"),
            pytest.param({".mthds/main.mthds": VALID_MTHDS}, "excluded_name", id="excluded-name"),
        ],
    )
    def test_a_files_member_that_is_no_method_tree_is_refused_as_validate_refuses_it(self, files: Any, refusal_code: str | None):
        client = _build_client()
        problem = _assert_problem(client.post(RESOLVE_PATH, json={"files": files}), status=422, error_type="InvalidMethodFiles")
        validate_problem = _assert_problem(client.post("/v1/validate", json={"files": files}), status=422, error_type="InvalidMethodFiles")
        if refusal_code is not None:
            assert problem["tree_refusal"]["code"] == refusal_code
        assert problem.get("tree_refusal") == validate_problem.get("tree_refusal")

    def test_a_hash_the_runner_does_not_hold_is_a_422_naming_it(self):
        notes = b"notes the runner never received"
        response = _build_client().post(RESOLVE_PATH, json={"files": {"main.mthds": VALID_MTHDS, "notes.txt": _hash_entry(notes)}})
        problem = _assert_problem(response, status=422, error_type="MissingBlobs")
        assert problem["missing_blobs"] == [sha256_hex(notes)]

    def test_a_file_past_the_tree_limit_is_refused(self):
        response = _build_client().post(RESOLVE_PATH, json={"files": {"main.mthds": VALID_MTHDS, "big.txt": "a" * (MAX_METHOD_TREE_FILE_BYTES + 1)}})
        problem = _assert_problem(response, status=422, error_type="MethodTreeTooLarge")
        assert "'big.txt'" in problem["detail"]

    def test_python_in_a_tree_is_refused_where_it_could_not_run(self):
        response = _build_client().post(RESOLVE_PATH, json={"files": {"main.mthds": VALID_MTHDS, "helpers/tool.py": "VALUE = 1\n"}})
        _assert_problem(response, status=403, error_type="CustomCodeRequiresSandbox")

    def test_a_tree_without_a_bundle_is_refused(self):
        response = _build_client().post(RESOLVE_PATH, json={"files": {"notes.txt": "no bundle here"}})
        _assert_problem(response, status=422, error_type="InvalidBundle")

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
