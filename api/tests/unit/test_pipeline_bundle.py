"""Route-level tests for the method-bundle transport on /execute and /start.

The pipeline runner is mocked (as in `test_pipeline_routes`); these assert that
the API layer KEEPS the proven run path for a bundle — the bundle's `.mthds` text
is passed as `mthds_contents` (so the engine resolves `main_pipe` exactly as for a
plain run) — while ONLY the non-`.mthds` files (custom PipeFunc `.py`, etc.) are
materialized into a temporary `library_dirs` directory for source capture, while the
method packages it ships under `.mthds/methods/<name>/` leave both and are written
into their own temporary `methods_dirs` directory. They also assert the custom-Python
sandbox gate, the both-forms guard, and the shapes of `.mthds/` content refused.
"""

import base64
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipelex.pipeline.pipeline_response import PipelexRunResultStart, RunState
from pytest_mock import MockerFixture

from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes.pipelex.pipeline import router as pipeline_router
from tests.unit._constants import (
    UNRESOLVED_PACKAGE_MTHDS,
    VALID_MTHDS,
    VENDORED_PROBE_ADDRESS,
    VENDORED_PROBE_FILES,
    VENDORED_PROBE_MANIFEST,
    VENDORED_PROBE_MTHDS,
)

_PIPE_FUNC_PY = "def echo(working_memory):\n    return 'hi'\n"

# Each `.mthds/` shape a request is refused for, with the text the refusal must name: the entry, or the package directory.
_REFUSED_VENDORING_SHAPES: dict[str, tuple[dict[str, str], str]] = {
    "a file under .mthds/ outside methods/": ({"bundle.mthds": UNRESOLVED_PACKAGE_MTHDS, ".mthds/foo": "x"}, ".mthds/foo"),
    "a .mthds/methods/ store below the root": (
        {"bundle.mthds": UNRESOLVED_PACKAGE_MTHDS, "sub/.mthds/methods/probe/probe.mthds": VENDORED_PROBE_MTHDS},
        "sub/.mthds/methods/probe/probe.mthds",
    ),
    "a file directly under .mthds/methods/": (
        {"bundle.mthds": UNRESOLVED_PACKAGE_MTHDS, ".mthds/methods/probe.mthds": VENDORED_PROBE_MTHDS},
        ".mthds/methods/probe.mthds",
    ),
    "a package shipping its own .mthds/ store": (
        {
            **VENDORED_PROBE_FILES,
            ".mthds/methods/probe/.mthds/methods/inner/inner.mthds": VENDORED_PROBE_MTHDS,
        },
        ".mthds/methods/probe/.mthds/methods/inner/inner.mthds",
    ),
    "a package directory without METHODS.toml": (
        {"bundle.mthds": UNRESOLVED_PACKAGE_MTHDS, ".mthds/methods/probe/probe.mthds": VENDORED_PROBE_MTHDS},
        ".mthds/methods/probe/",
    ),
    "a package whose METHODS.toml is not a manifest": (
        {**VENDORED_PROBE_FILES, ".mthds/methods/probe/METHODS.toml": "[package]\nname = 'probe'\n"},
        ".mthds/methods/probe/METHODS.toml",
    ),
    "a hidden package directory": (
        {
            "bundle.mthds": UNRESOLVED_PACKAGE_MTHDS,
            ".mthds/methods/.probe/METHODS.toml": VENDORED_PROBE_MANIFEST,
            ".mthds/methods/.probe/probe.mthds": VENDORED_PROBE_MTHDS,
        },
        ".mthds/methods/.probe/",
    ),
    "a request whose only .mthds files are vendored": (
        {".mthds/methods/probe/METHODS.toml": VENDORED_PROBE_MANIFEST, ".mthds/methods/probe/probe.mthds": VENDORED_PROBE_MTHDS},
        "no .mthds file of its own",
    ),
}


def _probe_manifest(*, address: str, name: str | None) -> str:
    """A manifest exporting the probe package's entry, declaring the address and, when given, the name."""
    name_line = f'name = "{name}"\n' if name is not None else ""
    package = f'[package]\n{name_line}address = "{address}"\nversion = "0.1.0"\ndescription = "A shipped package"\n'
    return f'{package}\n[exports.probe_dep]\npipes = ["entry"]\n'


def _shipped_packages(manifests: dict[str, str]) -> dict[str, str]:
    """A bundle calling the probe package and shipping one package per `{directory name: manifest}`."""
    files = {"bundle.mthds": UNRESOLVED_PACKAGE_MTHDS}
    for directory, manifest in manifests.items():
        files[f".mthds/methods/{directory}/METHODS.toml"] = manifest
        files[f".mthds/methods/{directory}/probe.mthds"] = VENDORED_PROBE_MTHDS
    return files


# Two shipped packages a reference could not tell apart, each with the directories the refusal must name. The identity
# is the one a reference is matched against: the address, then the manifest's name or else the directory's, without case.
_DUPLICATE_IDENTITY_BUNDLES: dict[str, tuple[dict[str, str], tuple[str, ...]]] = {
    "the same manifest twice": (_shipped_packages({"a": VENDORED_PROBE_MANIFEST, "b": VENDORED_PROBE_MANIFEST}), ("a", "b")),
    "one named by its directory, in another case": (
        _shipped_packages(
            {
                "first": _probe_manifest(address="github.com/invented/probe-lib", name="probe"),
                "Probe": _probe_manifest(address="github.com/Invented/Probe-Lib", name=None),
            }
        ),
        ("first", "Probe"),
    ),
}


def _files_under(directory: Path) -> list[str]:
    return sorted(path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file())


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

    def _record(runner_kwargs: dict[str, Any], run_kwargs: dict[str, Any]) -> None:
        library_dirs: list[str] | None = runner_kwargs.get("library_dirs")
        methods_dirs: list[Path] | None = runner_kwargs.get("methods_dirs")
        snapshot["library_dirs"] = library_dirs
        snapshot["methods_dirs"] = methods_dirs
        snapshot["mthds_contents"] = run_kwargs.get("mthds_contents")
        if library_dirs:
            root = Path(library_dirs[0])
            snapshot["dir_exists"] = root.exists()
            snapshot["files"] = _files_under(root)
        else:
            snapshot["files"] = None
        snapshot["methods_files"] = [_files_under(Path(methods_dir)) for methods_dir in methods_dirs] if methods_dirs else None

    def _make_runner(**kwargs: Any) -> Any:
        runner = mocker.MagicMock()

        async def _execute(**run_kwargs: Any) -> Any:
            _record(kwargs, run_kwargs)
            return fake_execute_response

        async def _start(**run_kwargs: Any) -> Any:
            _record(kwargs, run_kwargs)
            return PipelexRunResultStart(
                pipeline_run_id="run-1",
                created_at="2026-01-15T12:00:00Z",
                state=RunState.STARTED,
                workflow_id="wf-1",
            )

        runner.execute = _execute
        runner.start = _start
        return runner

    mocker.patch("pipelex_api.routes.pipelex.pipeline.ApiRunner", side_effect=_make_runner)
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
        mocker.patch("pipelex_api.routes.pipelex.pipeline.is_pipe_func_sandbox_hosted", return_value=False)
        client, _ = _build_client(mocker)
        response = client.post("/v1/execute", json={"files": {"main.mthds": VALID_MTHDS, "funcs/pipe_func.py": _PIPE_FUNC_PY}})
        assert response.status_code == 403
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "CustomCodeRequiresSandbox"

    def test_python_bundle_splits_mthds_from_py_when_hosted(self, mocker: MockerFixture):
        """The key fix: `.mthds` → `mthds_contents` (main_pipe path), ONLY the `.py`
        is materialized to the temp `library_dirs` for source capture.
        """
        mocker.patch("pipelex_api.routes.pipelex.pipeline.is_pipe_func_sandbox_hosted", return_value=True)
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

    @pytest.mark.parametrize(
        ("files", "named"),
        [
            pytest.param({"main.mthds": VALID_MTHDS, "notes.txt": "\ud800"}, "'notes.txt'", id="in-content"),
            pytest.param({"main.mthds": VALID_MTHDS, "notes\ud800.txt": "x"}, r"'notes\ud800.txt'", id="in-name"),
        ],
    )
    def test_a_files_entry_that_is_not_utf8_text_is_refused(self, mocker: MockerFixture, files: dict[str, str], named: str):
        """A lone surrogate rides JSON as an escape but has no UTF-8 form, so the entry is refused, never written."""
        client, snapshot = _build_client(mocker)
        # The escaped `\ud800` is valid JSON text, which `json=` would refuse to encode.
        raw_body = json.dumps({"files": files, "inputs": {"text": "hi"}})

        response = client.post("/v1/execute", content=raw_body, headers={"content-type": "application/json"})

        assert response.status_code == 422, response.text
        problem = response.json()
        assert problem["error_type"] == "InvalidBundle"
        assert named in problem["detail"]
        assert snapshot == {}, "the runner was reached"

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

    @pytest.mark.parametrize("transport", ["files", "bundle_b64"])
    @pytest.mark.parametrize("path", ["/v1/execute", "/v1/start"])
    def test_a_vendored_package_gets_its_own_methods_dir(self, mocker: MockerFixture, transport: str, path: str):
        """A package under `.mthds/methods/<name>/` leaves `mthds_contents` and the library dir for a methods dir of its own."""
        mocker.patch("pipelex_api.routes.pipelex.pipeline.is_pipe_func_sandbox_hosted", return_value=True)
        client, snapshot = _build_client(mocker)
        files = {**VENDORED_PROBE_FILES, "pipe_func.py": _PIPE_FUNC_PY}
        body: dict[str, Any] = {"files": files} if transport == "files" else {"bundle_b64": _zip_b64(files)}

        response = client.post(path, json={**body, "inputs": {"text": "hi"}})

        assert response.status_code in {200, 202}, response.text
        # The bundle's own file alone is the content; the package's bundle is not the caller's own domain.
        assert snapshot["mthds_contents"] == [UNRESOLVED_PACKAGE_MTHDS]
        # The library dir holds the bundle's own Python, and nothing of the package.
        assert snapshot["files"] == ["pipe_func.py"]
        # The package is in its own methods dir, laid out as `<name>/…`, a path no walk-up could take for a store.
        (methods_dir,) = snapshot["methods_dirs"]
        assert snapshot["methods_files"] == [["probe/METHODS.toml", "probe/probe.mthds"]]
        assert ".mthds/methods" not in Path(methods_dir).as_posix()
        # Cleaned once the request returns, like the library dir.
        assert not Path(methods_dir).exists()

    def test_a_bundle_shipping_no_package_gets_no_methods_dir(self, mocker: MockerFixture):
        client, snapshot = _build_client(mocker)
        response = client.post("/v1/execute", json={"files": {"main.mthds": VALID_MTHDS}, "inputs": {"text": "hi"}})
        assert response.status_code == 200
        assert snapshot["methods_dirs"] is None

    @pytest.mark.parametrize("transport", ["files", "bundle_b64"])
    @pytest.mark.parametrize("shape", list(_REFUSED_VENDORING_SHAPES))
    def test_a_misplaced_mthds_entry_is_refused(self, mocker: MockerFixture, transport: str, shape: str):
        """A `.mthds` path no reference could find is refused with the layout to use, never dropped."""
        files, named = _REFUSED_VENDORING_SHAPES[shape]
        client, snapshot = _build_client(mocker)
        body: dict[str, Any] = {"files": files} if transport == "files" else {"bundle_b64": _zip_b64(files)}

        response = client.post("/v1/execute", json={**body, "inputs": {"text": "hi"}})

        assert response.status_code == 422, response.text
        problem = response.json()
        assert problem["error_type"] == "InvalidBundle"
        assert named in problem["detail"]
        assert ".mthds/methods/<name>/" in problem["detail"]
        assert snapshot == {}, "the runner was reached"

    @pytest.mark.parametrize("transport", ["files", "bundle_b64"])
    @pytest.mark.parametrize("bundle", list(_DUPLICATE_IDENTITY_BUNDLES))
    def test_two_shipped_packages_of_one_identity_are_refused(self, mocker: MockerFixture, transport: str, bundle: str):
        """Which of two packages a reference would match is no choice to make by directory order: the bundle is refused."""
        files, directories = _DUPLICATE_IDENTITY_BUNDLES[bundle]
        client, snapshot = _build_client(mocker)
        body: dict[str, Any] = {"files": files} if transport == "files" else {"bundle_b64": _zip_b64(files)}

        response = client.post("/v1/execute", json={**body, "inputs": {"text": "hi"}})

        assert response.status_code == 422, response.text
        problem = response.json()
        assert problem["error_type"] == "InvalidBundle"
        assert VENDORED_PROBE_ADDRESS.casefold() in problem["detail"].casefold()
        for directory in directories:
            assert f"'.mthds/methods/{directory}/'" in problem["detail"]
        assert snapshot == {}, "the runner was reached"

    def test_two_shipped_packages_of_one_repository_are_both_shipped(self, mocker: MockerFixture):
        """Packages sharing an address but not a name are two identities, as two packages of one library repository are."""
        files = _shipped_packages(
            {
                "probe": VENDORED_PROBE_MANIFEST,
                "sibling": _probe_manifest(address="github.com/invented/probe-lib", name="sibling"),
            }
        )
        client, snapshot = _build_client(mocker)

        response = client.post("/v1/execute", json={"files": files, "inputs": {"text": "hi"}})

        assert response.status_code == 200, response.text
        assert snapshot["methods_files"] == [["probe/METHODS.toml", "probe/probe.mthds", "sibling/METHODS.toml", "sibling/probe.mthds"]]
