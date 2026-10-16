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

    @pytest.mark.parametrize("stated_size", ["exact", "wrong"])
    def test_a_hash_the_runner_does_not_hold_at_its_size_is_a_422_naming_it(self, mocker: MockerFixture, stated_size: str) -> None:
        client = _build_client(mocker)
        if stated_size == "wrong":
            _upload_all(client, _NOTES)
        notes_entry = {"sha256": sha256_hex(_NOTES), "size": len(_NOTES) + (1 if stated_size == "wrong" else 0)}

        response = client.post("/v1/execute", json={"files": {"greet.mthds": _GREET_MTHDS, "notes.txt": notes_entry}, "inputs": {"text": "x"}})

        assert response.status_code == 422, response.text
        problem = response.json()
        assert problem["error_type"] == "MissingBlobs"
        assert problem["missing_blobs"] == [sha256_hex(_NOTES)]
        assert "/v1/blobs/missing" in problem["detail"]

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
