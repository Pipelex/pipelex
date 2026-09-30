"""Route-level tests for the method-bundle transport on /execute and /start.

The pipeline runner is mocked (as in `test_pipeline_routes`); these assert that
the API layer KEEPS the proven run path for a bundle — the bundle's `.mthds` text
is passed as `mthds_contents` (so the engine resolves `main_pipe` exactly as for a
plain run) — while ONLY the non-`.mthds` files (custom PipeFunc `.py`, etc.) are
materialized into a temporary `library_dirs` directory for source capture. They
also assert the custom-Python sandbox gate and the both-forms guard.
"""

import base64
import io
import zipfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipelex.pipeline.pipeline_response import PipelexRunResultStart, RunState
from pytest_mock import MockerFixture

from api.exception_handlers import register_exception_handlers
from api.routes.pipelex.pipeline import router as pipeline_router
from tests.unit._constants import VALID_MTHDS

_PIPE_FUNC_PY = "def echo(working_memory):\n    return 'hi'\n"


def _zip_b64(files: dict[str, str]) -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _build_client(mocker: MockerFixture) -> tuple[TestClient, dict[str, Any]]:
    """Wire an app whose ApiRunner is mocked and records what the run actually saw.

    The `snapshot` captures BOTH what the runner was asked to run — the
    `mthds_contents` passed to `execute`/`start` — and the `library_dirs` it was
    constructed with plus the files on disk at run time. Together they prove the
    split: the `.mthds` travels as `mthds_contents`, only the `.py` hits disk, and
    the temp dir is torn down after the request.
    """
    app = FastAPI()
    app.include_router(pipeline_router, prefix="/v1")
    register_exception_handlers(app)

    snapshot: dict[str, Any] = {}

    fake_execute_response = mocker.MagicMock()
    # `/execute` now applies pipelex's `apply_tokens_usage_wire_shape` to the dump, which
    # rewrites `pipe_output.tokens_usages` — so the dump needs a `pipe_output` and the
    # response a `tokens_usages` (None here: these tests assert on the run path, not usage).
    fake_execute_response.model_dump.return_value = {
        "pipeline_run_id": "run-1",
        "state": "COMPLETED",
        "pipe_output": {"working_memory": {"root": {}, "aliases": {}}},
    }
    fake_execute_response.pipe_output.tokens_usages = None

    def _record(library_dirs: list[str] | None, run_kwargs: dict[str, Any]) -> None:
        snapshot["library_dirs"] = library_dirs
        snapshot["mthds_contents"] = run_kwargs.get("mthds_contents")
        if library_dirs:
            root = Path(library_dirs[0])
            snapshot["dir_exists"] = root.exists()
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


class TestPipelineBundle:
    def test_mthds_only_bundle_rides_mthds_contents_no_library_dir(self, mocker: MockerFixture):
        """A `.mthds`-only bundle takes the proven path: its text becomes `mthds_contents`
        (so `main_pipe` resolves as always) and NO temp library dir is created.
        """
        client, snapshot = _build_client(mocker)
        response = client.post("/v1/execute", json={"files": {"main.mthds": VALID_MTHDS}, "inputs": {"text": "hi"}})
        assert response.status_code == 200
        assert snapshot["mthds_contents"] == [VALID_MTHDS]
        assert snapshot["library_dirs"] is None

    def test_zip_bundle_rides_mthds_contents(self, mocker: MockerFixture):
        client, snapshot = _build_client(mocker)
        bundle = _zip_b64({"main.mthds": VALID_MTHDS})
        response = client.post("/v1/execute", json={"bundle_b64": bundle, "inputs": {"text": "hi"}})
        assert response.status_code == 200
        assert snapshot["mthds_contents"] == [VALID_MTHDS]
        assert snapshot["library_dirs"] is None

    def test_no_bundle_passes_request_mthds_contents(self, mocker: MockerFixture):
        client, snapshot = _build_client(mocker)
        response = client.post("/v1/execute", json={"pipe_code": "echo", "mthds_contents": [VALID_MTHDS], "inputs": {}})
        assert response.status_code == 200
        assert snapshot["library_dirs"] is None
        assert snapshot["mthds_contents"] == [VALID_MTHDS]

    def test_python_bundle_forbidden_when_not_hosted(self, mocker: MockerFixture):
        mocker.patch("api.routes.pipelex.pipeline.is_pipe_func_sandbox_hosted", return_value=False)
        client, _ = _build_client(mocker)
        response = client.post("/v1/execute", json={"files": {"main.mthds": VALID_MTHDS, "funcs/pipe_func.py": _PIPE_FUNC_PY}})
        assert response.status_code == 403
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "CustomCodeRequiresSandbox"

    def test_python_bundle_splits_mthds_from_py_when_hosted(self, mocker: MockerFixture):
        """The key fix: `.mthds` → `mthds_contents` (main_pipe path), ONLY the `.py`
        is materialized to the temp `library_dirs` for source capture.
        """
        mocker.patch("api.routes.pipelex.pipeline.is_pipe_func_sandbox_hosted", return_value=True)
        client, snapshot = _build_client(mocker)
        response = client.post("/v1/execute", json={"files": {"main.mthds": VALID_MTHDS, "funcs/pipe_func.py": _PIPE_FUNC_PY}})
        assert response.status_code == 200
        # The .mthds took the proven path, not the disk.
        assert snapshot["mthds_contents"] == [VALID_MTHDS]
        # Only the Python landed in the library dir.
        assert snapshot["files"] == ["funcs/pipe_func.py"]
        assert snapshot["dir_exists"] is True
        # Temp dir is cleaned once the request returns.
        assert not Path(snapshot["library_dirs"][0]).exists()

    def test_both_forms_rejected_via_route(self, mocker: MockerFixture):
        client, _ = _build_client(mocker)
        response = client.post(
            "/v1/execute",
            json={"files": {"main.mthds": VALID_MTHDS}, "bundle_b64": _zip_b64({"main.mthds": VALID_MTHDS})},
        )
        assert response.status_code == 422
        assert response.json()["error_type"] == "InvalidBundle"

    def test_start_bundle_rides_mthds_contents(self, mocker: MockerFixture):
        client, snapshot = _build_client(mocker)
        response = client.post("/v1/start", json={"files": {"main.mthds": VALID_MTHDS}, "inputs": {"text": "hi"}})
        assert response.status_code == 202
        assert snapshot["mthds_contents"] == [VALID_MTHDS]
        assert snapshot["library_dirs"] is None

    def test_bundle_and_mthds_contents_are_mutually_exclusive(self, mocker: MockerFixture):
        client, _ = _build_client(mocker)
        response = client.post(
            "/v1/execute",
            json={"files": {"main.mthds": VALID_MTHDS}, "mthds_contents": [VALID_MTHDS]},
        )
        assert response.status_code == 422
        assert "mutually exclusive" in response.text
