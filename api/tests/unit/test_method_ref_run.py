"""Route-level tests for `method_ref` as a run source on /execute and /start.

The pipeline runner is mocked (as in `test_pipeline_bundle`) and the clone cache is stubbed
with a local directory tree (`install_method_package` in conftest), so these pin the API
layer's contract: the fetched package's `.mthds` files ride `mthds_contents`, the entry pipe
defaults to the manifest's `main_pipe` (a request `pipe_code` overrides), provenance
`{address, tag, commit_sha}` lands on the response, the exclusivity rules 422, the
execution-locus gate refuses Python where it must, and each resolution failure maps to its
distinct `error_type` + status as RFC 7807 `problem+json`.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipelex.methods.exceptions import MethodFetchError
from pipelex.pipeline.pipeline_response import PipelexRunResultStart, RunState
from pytest_mock import MockerFixture

from api.exception_handlers import register_exception_handlers
from api.routes.pipelex.pipeline import router as pipeline_router
from tests.unit._constants import STUB_METHOD_ADDRESS, STUB_METHOD_COMMIT_SHA, VALID_MTHDS

_METHOD_REF = f"{STUB_METHOD_ADDRESS}@v0.1.0"

_PIPE_FUNC_PY = "def echo(working_memory):\n    return 'hi'\n"

_STRUCTURES_PY = """\
from pipelex.core.stuffs.structured_content import StructuredContent


class Invoice(StructuredContent):
    total: float
"""


def _build_client(mocker: MockerFixture) -> tuple[TestClient, dict[str, Any]]:
    """Wire an app whose ApiRunner is mocked and records what the run actually saw."""
    app = FastAPI()
    app.include_router(pipeline_router, prefix="/v1")
    register_exception_handlers(app)

    snapshot: dict[str, Any] = {}

    fake_execute_response = mocker.MagicMock()
    fake_execute_response.model_dump.return_value = {
        "pipeline_run_id": "run-1",
        "state": "COMPLETED",
        "pipe_output": {"working_memory": {"root": {}, "aliases": {}}},
    }
    fake_execute_response.pipe_output.tokens_usages = None

    def _record(library_dirs: list[str] | None, run_kwargs: dict[str, Any]) -> None:
        snapshot["library_dirs"] = library_dirs
        snapshot["mthds_contents"] = run_kwargs.get("mthds_contents")
        snapshot["pipe_code"] = run_kwargs.get("pipe_code")
        if library_dirs:
            root = Path(library_dirs[0])
            snapshot["files"] = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
        else:
            snapshot["files"] = None

    def _make_runner(**kwargs: Any) -> Any:
        library_dirs: list[str] | None = kwargs.get("library_dirs")
        runner = mocker.MagicMock()

        async def _execute(**run_kwargs: Any) -> Any:
            _record(library_dirs, run_kwargs)
            return fake_execute_response

        async def _start(**run_kwargs: Any) -> Any:
            _record(library_dirs, run_kwargs)
            return PipelexRunResultStart(
                pipeline_run_id="run-1",
                created_at="2026-01-15T12:00:00Z",
                state=RunState.STARTED,
                workflow_id="wf-1",
            )

        runner.execute = _execute
        runner.start = _start
        return runner

    mocker.patch("api.routes.pipelex.pipeline.ApiRunner", side_effect=_make_runner)
    return TestClient(app), snapshot


class TestMethodRefRun:
    def test_execute_rides_fetched_contents_defaults_main_pipe_and_carries_provenance(
        self, mocker: MockerFixture, install_method_package: Callable[..., Path]
    ):
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        client, snapshot = _build_client(mocker)
        response = client.post("/v1/execute", json={"method_ref": _METHOD_REF, "inputs": {"text": "hi"}})
        assert response.status_code == 200, response.text
        # The package's `.mthds` took the proven inline path; no Python → no library dir.
        assert snapshot["mthds_contents"] == [VALID_MTHDS]
        assert snapshot["library_dirs"] is None
        # The entry pipe came from the manifest's `main_pipe`.
        assert snapshot["pipe_code"] == "echo"
        # Provenance: resolved full address, the requested tag, the fetched commit SHA.
        assert response.json()["method_provenance"] == {
            "address": STUB_METHOD_ADDRESS,
            "tag": "v0.1.0",
            "commit_sha": STUB_METHOD_COMMIT_SHA,
        }

    def test_request_pipe_code_overrides_manifest_main_pipe(self, mocker: MockerFixture, install_method_package: Callable[..., Path]):
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        client, snapshot = _build_client(mocker)
        response = client.post("/v1/execute", json={"method_ref": _METHOD_REF, "pipe_code": "smoke.echo", "inputs": {"text": "hi"}})
        assert response.status_code == 200, response.text
        assert snapshot["pipe_code"] == "smoke.echo"

    def test_start_carries_provenance_on_the_ack(self, mocker: MockerFixture, install_method_package: Callable[..., Path]):
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        client, snapshot = _build_client(mocker)
        response = client.post("/v1/start", json={"method_ref": STUB_METHOD_ADDRESS, "inputs": {"text": "hi"}})
        assert response.status_code == 202, response.text
        assert snapshot["mthds_contents"] == [VALID_MTHDS]
        body = response.json()
        assert body["pipeline_run_id"] == "run-1"
        # A bare address: provenance records tag=None and the resolved HEAD commit.
        assert body["method_provenance"] == {"address": STUB_METHOD_ADDRESS, "tag": None, "commit_sha": STUB_METHOD_COMMIT_SHA}

    def test_inline_runs_carry_no_provenance(self, mocker: MockerFixture):
        client, _ = _build_client(mocker)
        execute_response = client.post("/v1/execute", json={"mthds_contents": [VALID_MTHDS], "inputs": {"text": "hi"}})
        assert execute_response.status_code == 200
        assert "method_provenance" not in execute_response.json()
        start_response = client.post("/v1/start", json={"mthds_contents": [VALID_MTHDS], "inputs": {"text": "hi"}})
        assert start_response.status_code == 202
        assert start_response.json()["method_provenance"] is None

    def test_method_ref_is_exclusive_with_inline_contents_and_bundles(self, mocker: MockerFixture, install_method_package: Callable[..., Path]):
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        client, _ = _build_client(mocker)
        with_contents = client.post("/v1/execute", json={"method_ref": _METHOD_REF, "mthds_contents": [VALID_MTHDS]})
        with_bundle = client.post("/v1/execute", json={"method_ref": _METHOD_REF, "files": {"main.mthds": VALID_MTHDS}})
        for response in (with_contents, with_bundle):
            assert response.status_code == 422, response.text
            assert "mutually exclusive" in response.json()["detail"]

    def test_malformed_ref_is_422_with_parse_error_type(self, mocker: MockerFixture, install_method_package: Callable[..., Path]):
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        client, _ = _build_client(mocker)
        response = client.post("/v1/execute", json={"method_ref": "gitlab.com/acme/tools", "inputs": {}})
        assert response.status_code == 422, response.text
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "MethodRefParseError"

    def test_unknown_package_is_404_problem_json(self, mocker: MockerFixture, install_method_package: Callable[..., Path]):
        install_method_package(files={"documents.mthds": VALID_MTHDS})
        client, _ = _build_client(mocker)
        response = client.post("/v1/execute", json={"method_ref": "github.com/pipelex/methods/nonexistent", "inputs": {}})
        assert response.status_code == 404, response.text
        assert response.headers["content-type"] == "application/problem+json"
        body = response.json()
        assert body["error_type"] == "MethodPackageNotFoundError"
        # The message teaches: it lists the packages the repository does contain.
        assert STUB_METHOD_ADDRESS in body["detail"]

    def test_fetch_failure_is_422_with_fetch_error_type(self, mocker: MockerFixture):
        stub_cache = mocker.MagicMock()
        stub_cache.get_or_fetch.side_effect = MethodFetchError("Failed to fetch method 'github.com/pipelex/methods/documents': boom")
        mocker.patch("api.method_source.get_method_clone_cache", return_value=stub_cache)
        client, _ = _build_client(mocker)
        response = client.post("/v1/execute", json={"method_ref": STUB_METHOD_ADDRESS, "inputs": {}})
        assert response.status_code == 422, response.text
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "MethodFetchError"

    def test_python_package_forbidden_when_not_sandbox_hosted(self, mocker: MockerFixture, install_method_package: Callable[..., Path]):
        install_method_package(files={"documents.mthds": VALID_MTHDS, "funcs/pipe_func.py": _PIPE_FUNC_PY})
        mocker.patch("api.method_source.is_pipe_func_sandbox_hosted", return_value=False)
        client, _ = _build_client(mocker)
        response = client.post("/v1/execute", json={"method_ref": _METHOD_REF, "inputs": {}})
        assert response.status_code == 403, response.text
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "CustomCodeRequiresSandbox"

    def test_python_package_splits_mthds_from_py_when_sandbox_hosted(self, mocker: MockerFixture, install_method_package: Callable[..., Path]):
        install_method_package(files={"documents.mthds": VALID_MTHDS, "funcs/pipe_func.py": _PIPE_FUNC_PY})
        mocker.patch("api.method_source.is_pipe_func_sandbox_hosted", return_value=True)
        client, snapshot = _build_client(mocker)
        response = client.post("/v1/execute", json={"method_ref": _METHOD_REF, "inputs": {}})
        assert response.status_code == 200, response.text
        # `.mthds` rides mthds_contents; ONLY the Python lands in the temp library dir — the
        # manifest is consumed (identity + main_pipe) and deliberately NOT materialized.
        assert snapshot["mthds_contents"] == [VALID_MTHDS]
        assert snapshot["files"] == ["funcs/pipe_func.py"]
        # The temp dir is cleaned once the request returns.
        assert not Path(snapshot["library_dirs"][0]).exists()

    def test_structures_package_refused_even_when_sandbox_hosted(self, mocker: MockerFixture, install_method_package: Callable[..., Path]):
        install_method_package(files={"documents.mthds": VALID_MTHDS, "structures/models.py": _STRUCTURES_PY})
        mocker.patch("api.method_source.is_pipe_func_sandbox_hosted", return_value=True)
        client, _ = _build_client(mocker)
        response = client.post("/v1/execute", json={"method_ref": _METHOD_REF, "inputs": {}})
        assert response.status_code == 403, response.text
        assert response.headers["content-type"] == "application/problem+json"
        body = response.json()
        assert body["error_type"] == "MethodStructuresRefusedError"
        # The refusal names the rule and teaches the fix.
        assert "MTHDS concepts" in body["detail"]
