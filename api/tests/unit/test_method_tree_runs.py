"""A method sent as a tree, each file inline or by hash, run and validated by the real routes and runner.

The in-process orchestrator runs the method, whose only step composes a text, so what the run answers is what the
engine loaded from the tree it was sent. Hash entries resolve in the caller's own blob store, the in-memory one the
conftest installs, filled through the blob routes as a sender fills it. A refusal of the caller's own tree is the
caller's to read: a 422 naming files by their tree paths, never by the directory the runner wrote the tree into.
"""

import base64
import json
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mthds.method_tree.digest import sha256_hex
from pipelex.config import get_config
from pytest_mock import MockerFixture

from pipelex_api.api_config import ApiConfig
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router
from pipelex_api.routes.blob_upload import router as blob_upload_router

_PIPELINE_NS = "pipelex_api.routes.pipelex.pipeline"

_GREET_MTHDS = """\
domain = "greeting"
main_pipe = "greet"

[pipe.greet]
type = "PipeCompose"
description = "Greet"
inputs = { text = "Text" }
output = "Text"
template = "Hello $text"
"""

_BROKEN_MTHDS = 'domain = "broken"\n\n[pipe.oops\ntype = "PipeCompose"\n'

_DEPENDENCY_ADDRESS = "github.com/acme/methods/library"
_DEPENDENCY_MANIFEST = """\
[package]
name = "library"
address = "github.com/acme/methods"
version = "0.1.0"
description = "A dependency a request sends beside its method."
"""

_NOTES = b"Some notes \xe2\x80\x94 kept with the method"
_ICON = b"\x89PNG\r\n\x1a\n not text"


@pytest.fixture(name="sandbox_hosted_mode")
def sandbox_hosted_mode_fixture() -> Generator[None, None, None]:
    """Select a non-`direct` PipeFunc execution mode, which makes the deployment sandbox-hosted for the route and the loader alike."""
    pipe_func_config = get_config().interpreter.pipe_func
    previous = pipe_func_config.execution_mode
    pipe_func_config.execution_mode = "sandbox"
    try:
        yield
    finally:
        pipe_func_config.execution_mode = previous


def _build_client(mocker: MockerFixture) -> TestClient:
    mocker.patch(
        f"{_PIPELINE_NS}.get_api_config", return_value=ApiConfig(orchestration_mode="direct", allow_request_orchestration_mode_override=False)
    )
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    app.include_router(blob_upload_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


def _hash_entry(data: bytes) -> dict[str, Any]:
    return {"sha256": sha256_hex(data), "size": len(data)}


def _upload_all(client: TestClient, *blobs: bytes, read_scope: str | None = None) -> None:
    """Upload every blob the runner lacks, as a sender does before sending hash entries."""
    params = {"read_scope": read_scope} if read_scope is not None else None
    response = client.post("/v1/blobs/missing", json={"blobs": [_hash_entry(data) for data in blobs]}, params=params)
    assert response.status_code == 200, response.text
    by_hash = {sha256_hex(data): data for data in blobs}
    for blob in response.json()["missing"]:
        upload = blob["upload"]
        uploaded = client.request(upload["method"], upload["url"], content=by_hash[blob["sha256"]], headers=upload["headers"])
        assert uploaded.status_code == 204, uploaded.text


def _run_output(body: dict[str, Any]) -> str:
    return json.dumps(body["pipe_output"]["working_memory"])


def _assert_no_host_path(body: Any) -> None:
    dump = json.dumps(body)
    assert "pipelex-method-" not in dump
    for temporary_root in (tempfile.gettempdir(), str(Path(tempfile.gettempdir()).resolve())):
        assert temporary_root not in dump


class TestMethodTreeRuns:
    def test_a_method_sent_with_every_entry_form_runs(self, mocker: MockerFixture) -> None:
        """A bundle by hash, a binary file in Base64 and a text file inline make one tree, run from its entry pipe."""
        client = _build_client(mocker)
        _upload_all(client, _GREET_MTHDS.encode("utf-8"))
        files = {
            "greet.mthds": _hash_entry(_GREET_MTHDS.encode("utf-8")),
            "assets/icon.png": {"base64": base64.b64encode(_ICON).decode("ascii")},
            "notes.txt": _NOTES.decode("utf-8"),
        }

        response = client.post("/v1/execute", json={"files": files, "inputs": {"text": "world"}})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["state"] == "COMPLETED"
        assert "Hello world" in _run_output(body)

    def test_a_hash_the_runner_does_not_hold_is_a_422_naming_it(self, mocker: MockerFixture) -> None:
        client = _build_client(mocker)

        response = client.post(
            "/v1/execute", json={"files": {"greet.mthds": _GREET_MTHDS, "notes.txt": _hash_entry(_NOTES)}, "inputs": {"text": "x"}}
        )

        assert response.status_code == 422, response.text
        problem = response.json()
        assert problem["error_type"] == "MissingBlobs"
        assert problem["missing_blobs"] == [sha256_hex(_NOTES)]
        assert "/v1/blobs/missing" in problem["detail"]

    def test_a_size_other_than_the_held_bytes_is_a_mismatch_no_upload_repeats(self, mocker: MockerFixture) -> None:
        """A sender following the answers, asking which blobs are missing and uploading them, ends at the mismatch, never in a loop."""
        client = _build_client(mocker)
        _upload_all(client, _NOTES)
        wrong_entry = {"sha256": sha256_hex(_NOTES), "size": len(_NOTES) + 1}
        body = {"files": {"greet.mthds": _GREET_MTHDS, "notes.txt": wrong_entry}, "inputs": {"text": "x"}}

        first = client.post("/v1/execute", json=body)
        asked = client.post("/v1/blobs/missing", json={"blobs": [wrong_entry]})
        (target,) = asked.json()["missing"]
        upload = target["upload"]
        uploaded = client.request(upload["method"], upload["url"], content=_NOTES, headers=upload["headers"])
        again = client.post("/v1/execute", json=body)

        assert uploaded.status_code == 204, uploaded.text
        for response in (first, again):
            assert response.status_code == 422, response.text
            problem = response.json()
            assert problem["error_type"] == "BlobMismatch"
            assert problem["mismatched_blobs"] == [{"sha256": sha256_hex(_NOTES), "held_size": len(_NOTES)}]

    def test_a_hash_resolves_only_in_the_callers_own_scope(self, mocker: MockerFixture) -> None:
        client = _build_client(mocker)
        _upload_all(client, _GREET_MTHDS.encode("utf-8"), read_scope="org-a")
        files = {"greet.mthds": _hash_entry(_GREET_MTHDS.encode("utf-8"))}

        own = client.post("/v1/execute", json={"files": files, "inputs": {"text": "a"}, "read_scope": "org-a", "storage_scope": "org-a"})
        other = client.post("/v1/execute", json={"files": files, "inputs": {"text": "b"}, "read_scope": "org-b", "storage_scope": "org-b"})

        assert own.status_code == 200, own.text
        assert "Hello a" in _run_output(own.json())
        assert other.status_code == 422, other.text
        assert other.json()["error_type"] == "MissingBlobs"

    def test_a_callers_bundle_that_does_not_parse_is_its_422_named_by_tree_path(self, mocker: MockerFixture) -> None:
        """The written tree is the caller's own library directory, so its refusal is the caller's 422, never the runner's 500."""
        client = _build_client(mocker)
        files = {"methods/greet.mthds": _GREET_MTHDS, "methods/broken.mthds": _BROKEN_MTHDS}

        response = client.post("/v1/execute", json={"files": files, "pipe_code": "greeting.greet", "inputs": {"text": "x"}})

        assert response.status_code == 422, response.text
        body = response.json()
        assert body["error_type"] == "ValidateBundleError"
        assert {item["source"] for item in body["validation_errors"]} == {"methods/broken.mthds"}
        _assert_no_host_path(body)

    def test_validate_a_method_tree_sent_as_files(self, mocker: MockerFixture) -> None:
        client = _build_client(mocker)

        response = client.post("/v1/validate", json={"files": {"greet.mthds": _GREET_MTHDS, "notes.txt": _NOTES.decode("utf-8")}})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True, body
        assert body["mthds_contents"] == [_GREET_MTHDS]
        assert body["default_pipe_ref"] == "greeting.greet"
        assert body["graph_spec"] is not None

    def test_validate_a_method_tree_whose_bundle_does_not_parse_is_an_invalid_verdict_named_by_tree_path(self, mocker: MockerFixture) -> None:
        client = _build_client(mocker)

        response = client.post("/v1/validate", json={"files": {"greet.mthds": _GREET_MTHDS, "methods/broken.mthds": _BROKEN_MTHDS}})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        assert {item["source"] for item in body["validation_errors"]} == {"methods/broken.mthds"}
        _assert_no_host_path(body)

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_validate_reads_every_python_file_of_the_tree_for_its_syntax(self, mocker: MockerFixture) -> None:
        """No step names the module, yet the validation of the whole tree finds its syntax error, by tree path and line."""
        client = _build_client(mocker)
        files = {"greet.mthds": _GREET_MTHDS, "helpers/broken.py": "def ok():\n    return 1\n\ndef oops(:\n    pass\n"}

        response = client.post("/v1/validate", json={"files": files})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False, body
        (item,) = body["validation_errors"]
        assert item["source"] == "helpers/broken.py"
        assert item["line"] == 4
        _assert_no_host_path(body)

    def test_python_in_a_tree_is_refused_where_it_could_not_run(self, mocker: MockerFixture) -> None:
        client = _build_client(mocker)

        response = client.post("/v1/validate", json={"files": {"greet.mthds": _GREET_MTHDS, "helpers/tool.py": "VALUE = 1\n"}})

        assert response.status_code == 403, response.text
        assert response.json()["error_type"] == "CustomCodeRequiresSandbox"

    def test_a_json_constant_outside_the_tree_is_never_a_server_error(self, mocker: MockerFixture) -> None:
        """`NaN` is the rest of the server's to judge where it stands outside a map of file entries, and a 422 inside one."""
        client = _build_client(mocker)
        files = json.dumps({"greet.mthds": _GREET_MTHDS})
        headers = {"content-type": "application/json"}

        inline = client.post("/v1/execute", content=f'{{"mthds_contents": {json.dumps([_GREET_MTHDS])}, "inputs": {{"text": NaN}}}}', headers=headers)
        beside_a_tree = client.post("/v1/execute", content=f'{{"files": {files}, "inputs": {{"text": NaN}}}}', headers=headers)
        inside_the_tree = client.post("/v1/execute", content='{"files": {"greet.mthds": NaN}, "inputs": {"text": "x"}}', headers=headers)

        for response in (inline, beside_a_tree):
            assert response.status_code == 422, response.text
            assert response.json()["error_type"] == "WrongScalarKindError"
        assert inside_the_tree.status_code == 422, inside_the_tree.text
        assert inside_the_tree.json()["error_type"] == "InvalidMethodFiles"

    @pytest.mark.parametrize("encoding", ["utf-16", "utf-32", "utf-8-sig"])
    def test_validate_reads_a_tree_from_a_body_in_any_json_encoding(self, mocker: MockerFixture, encoding: str) -> None:
        client = _build_client(mocker)
        body = json.dumps({"files": {"greet.mthds": _GREET_MTHDS, "notes.txt": _NOTES.decode("utf-8")}}).encode(encoding)

        response = client.post("/v1/validate", content=body, headers={"content-type": "application/json"})

        assert response.status_code == 200, response.text
        assert response.json()["is_valid"] is True, response.text

    def test_a_bundle_that_is_not_utf8_text_is_the_callers_located_diagnostic(self, mocker: MockerFixture) -> None:
        client = _build_client(mocker)
        files = {"greet.mthds": _GREET_MTHDS, "bad.mthds": {"base64": "/w=="}}

        run = client.post("/v1/execute", json={"files": files, "pipe_code": "greeting.greet", "inputs": {"text": "x"}})
        run_from_the_entry = client.post("/v1/execute", json={"files": files, "inputs": {"text": "x"}})
        validated = client.post("/v1/validate", json={"files": files})

        assert run.status_code == 422, run.text
        assert run.json()["error_type"] == "ValidateBundleError"
        assert [(item["source"], item["line"], item["column"]) for item in run.json()["validation_errors"]] == [("bad.mthds", 1, 1)]
        assert run_from_the_entry.status_code == 422, run_from_the_entry.text
        assert run_from_the_entry.json()["error_type"] == "MethodEntryError"
        assert "'bad.mthds'" in run_from_the_entry.json()["detail"]
        assert validated.status_code == 200, validated.text
        verdict = validated.json()
        assert verdict["is_valid"] is False
        assert [item["source"] for item in verdict["validation_errors"]] == ["bad.mthds"]
        _assert_no_host_path(verdict)

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_validate_reports_a_python_file_holding_a_nul_byte_at_its_tree_path(self, mocker: MockerFixture) -> None:
        """Python 3.11 refuses a NUL byte with a ValueError where later versions raise a SyntaxError: both are the file's verdict."""
        client = _build_client(mocker)

        response = client.post("/v1/validate", json={"files": {"greet.mthds": _GREET_MTHDS, "helpers/nul.py": "x = 1\u0000\n"}})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False, body
        assert [item["source"] for item in body["validation_errors"]] == ["helpers/nul.py"]

    def test_files_sent_in_resources_are_held_to_the_tree_limits(self, mocker: MockerFixture) -> None:
        mocker.patch("pipelex_api.method_tree_request.MAX_METHOD_TREE_FILES", 2)
        client = _build_client(mocker)
        files = {"greet.mthds": _GREET_MTHDS, "notes.txt": _NOTES.decode("utf-8")}

        within = client.post("/v1/validate", json={"files": files})
        past = client.post("/v1/validate", json={"files": files, "resources": {"extra.txt": base64.b64encode(b"one more").decode("ascii")}})

        assert within.status_code == 200, within.text
        assert past.status_code == 422, past.text
        assert past.json()["error_type"] == "MethodTreeTooLarge"
        assert "`resources`" in past.json()["detail"]

    @pytest.mark.parametrize(
        ("limit", "value"),
        [("MAX_METHOD_DEPENDENCIES", 0), ("MAX_METHOD_REQUEST_TOTAL_BYTES", len(_GREET_MTHDS) + 10)],
    )
    def test_a_method_and_its_dependencies_are_held_to_limits_together(self, mocker: MockerFixture, limit: str, value: int) -> None:
        """Each tree passes its own limits, yet the request carries too many trees, or too many bytes across them."""
        mocker.patch(f"pipelex_api.method_tree_request.{limit}", value)
        client = _build_client(mocker)
        dependency = {"METHODS.toml": _DEPENDENCY_MANIFEST, "lib.mthds": _GREET_MTHDS.replace('"greeting"', '"library"')}

        response = client.post("/v1/validate", json={"files": {"greet.mthds": _GREET_MTHDS}, "dependencies": {_DEPENDENCY_ADDRESS: dependency}})

        assert response.status_code == 422, response.text
        assert response.json()["error_type"] == "MethodTreeTooLarge"

    @pytest.mark.parametrize("last_segment", ["..", "."])
    def test_a_nameless_dependency_keyed_by_an_address_no_directory_can_take_is_refused(self, mocker: MockerFixture, last_segment: str) -> None:
        client = _build_client(mocker)
        nameless_manifest = _DEPENDENCY_MANIFEST.replace('name = "library"\n', "")
        dependency = {"METHODS.toml": nameless_manifest, "lib.mthds": _GREET_MTHDS.replace('"greeting"', '"library"')}
        address = f"{_DEPENDENCY_ADDRESS.rsplit('/', 1)[0]}/{last_segment}"

        response = client.post("/v1/validate", json={"files": {"greet.mthds": _GREET_MTHDS}, "dependencies": {address: dependency}})

        assert response.status_code == 422, response.text
        problem = response.json()
        assert problem["error_type"] == "InvalidMethodFiles"
        assert "cannot name a package's directory" in problem["detail"]
