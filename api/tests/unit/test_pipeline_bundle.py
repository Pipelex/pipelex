"""Route-level tests for a method sent as a tree on /execute and /start: a `files` map, or a `bundle_b64` archive.

The pipeline runner is mocked (as in `test_pipeline_routes`); these assert that the API layer
reads the method as a method tree, by the one rule of the tree, and writes it WHOLE into a
temporary directory handed to the runner as its one library directory, the caller's own, its
entry pipe chosen by the MTHDS protocol's rule. The dependencies it carries, as `dependencies`
beside `files` or under `.mthds/methods/<name>/` in an archive, are written into a methods
directory of their own. They also assert the custom-Python sandbox gate, the both-forms guard,
and the refusals of a map that is not a tree, each naming the entry it refuses.
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
_TREE_NS = "pipelex_api.method_tree_request"

# The probe package as a dependency tree of its own, its files at its root.
_PROBE_TREE: dict[str, str] = {"METHODS.toml": VENDORED_PROBE_MANIFEST, "probe.mthds": VENDORED_PROBE_MTHDS}

# Each `.mthds/` shape an archive is refused for, with the text the refusal must name: an entry the tree's rule refuses, or
# the package directory a dependency tree must be.
_REFUSED_ARCHIVE_SHAPES: dict[str, tuple[dict[str, str], str]] = {
    "a file under .mthds/ outside methods/": ({"bundle.mthds": UNRESOLVED_PACKAGE_MTHDS, ".mthds/foo": "x"}, "'.mthds/foo'"),
    "a .mthds/methods/ store below the root": (
        {"bundle.mthds": UNRESOLVED_PACKAGE_MTHDS, "sub/.mthds/methods/probe/probe.mthds": VENDORED_PROBE_MTHDS},
        "'sub/.mthds/methods/probe/probe.mthds'",
    ),
    "a file directly under .mthds/methods/": (
        {"bundle.mthds": UNRESOLVED_PACKAGE_MTHDS, ".mthds/methods/probe.mthds": VENDORED_PROBE_MTHDS},
        "'.mthds/methods/probe.mthds'",
    ),
    "a package shipping its own .mthds/ store": (
        {
            **VENDORED_PROBE_FILES,
            ".mthds/methods/probe/.mthds/methods/inner/inner.mthds": VENDORED_PROBE_MTHDS,
        },
        "'.mthds/methods/inner/inner.mthds'",
    ),
    "a hidden package directory": (
        {
            "bundle.mthds": UNRESOLVED_PACKAGE_MTHDS,
            ".mthds/methods/.probe/METHODS.toml": VENDORED_PROBE_MANIFEST,
            ".mthds/methods/.probe/probe.mthds": VENDORED_PROBE_MTHDS,
        },
        "'.mthds/methods/.probe/METHODS.toml'",
    ),
}

# A shipped package an archive is refused for, with the text the refusal must name.
_REFUSED_ARCHIVE_PACKAGES: dict[str, tuple[dict[str, str], str]] = {
    "a package directory without METHODS.toml": (
        {"bundle.mthds": UNRESOLVED_PACKAGE_MTHDS, ".mthds/methods/probe/probe.mthds": VENDORED_PROBE_MTHDS},
        ".mthds/methods/probe/",
    ),
    "a package whose METHODS.toml is not a manifest": (
        {**VENDORED_PROBE_FILES, ".mthds/methods/probe/METHODS.toml": "[package]\nname = 'probe'\n"},
        ".mthds/methods/probe/",
    ),
}


def _probe_manifest(*, address: str, name: str | None) -> str:
    """A manifest exporting the probe package's entry, declaring the address and, when given, the name."""
    name_line = f'name = "{name}"\n' if name is not None else ""
    package = f'[package]\n{name_line}address = "{address}"\nversion = "0.1.0"\ndescription = "A shipped package"\n'
    return f'{package}\n[exports.probe_dep]\npipes = ["entry"]\n'


def _shipped_packages(manifests: dict[str, str]) -> dict[str, str]:
    """A bundle calling the probe package and shipping one package per `{directory name: manifest}` in an archive's layout."""
    files = {"bundle.mthds": UNRESOLVED_PACKAGE_MTHDS}
    for directory, manifest in manifests.items():
        files[f".mthds/methods/{directory}/METHODS.toml"] = manifest
        files[f".mthds/methods/{directory}/probe.mthds"] = VENDORED_PROBE_MTHDS
    return files


# Two shipped packages a reference could not tell apart, with the address the refusal must name. The identity is the one a
# reference is matched against: the address, then the manifest's name or else the directory's, without case.
_DUPLICATE_IDENTITY_BUNDLES: dict[str, dict[str, str]] = {
    "the same manifest twice": _shipped_packages({"a": VENDORED_PROBE_MANIFEST, "b": VENDORED_PROBE_MANIFEST}),
    "one named by its directory, in another case": _shipped_packages(
        {
            "first": _probe_manifest(address="github.com/invented/probe-lib", name="probe"),
            "Probe": _probe_manifest(address="github.com/Invented/Probe-Lib", name=None),
        }
    ),
}


# Entries the tree's rule refuses, with the tree refusal code and the key the refusal must name. Each name is spelled
# differently, so the entries fit a `files` map as well as a zip.
_REFUSED_ENTRIES: dict[str, tuple[list[tuple[str, str]], str, str]] = {
    "a file named with a dot segment": ([("main.mthds", VALID_MTHDS), ("notes.txt", "a"), ("./notes.txt", "b")], "invalid_tree_path", "./notes.txt"),
    "a file named with an empty segment": ([("main.mthds", VALID_MTHDS), ("notes//a.txt", "a")], "invalid_tree_path", "notes//a.txt"),
    "a file that is another entry's directory": (
        [("main.mthds", VALID_MTHDS), ("helper.txt", "x"), ("helper.txt/inner.txt", "y")],
        "path_collision",
        "helper.txt",
    ),
    "a dotfile": ([("main.mthds", VALID_MTHDS), (".env", "x")], "excluded_name", ".env"),
    "a package in the local store layout": (
        [("main.mthds", VALID_MTHDS), *((f".mthds/methods/probe/{name}", text) for name, text in _PROBE_TREE.items())],
        "excluded_name",
        ".mthds/methods/probe/METHODS.toml",
    ),
}


def _files_under(directory: Path) -> list[str]:
    return sorted(path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file())


def _zip_b64(files: dict[str, str]) -> str:
    return _zip_b64_of_entries(list(files.items()))


def _zip_b64_of_entries(entries: list[tuple[str, str]]) -> str:
    """A zip of the entries in order, which, unlike a `files` map, may hold one member name twice."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _build_client(mocker: MockerFixture) -> tuple[TestClient, dict[str, Any]]:
    """Wire an app whose ApiRunner is mocked and records what the run actually saw.

    The `snapshot` captures BOTH what the runner was asked to run — the
    `mthds_contents` and `pipe_code` passed to `execute`/`start` — and the
    `library_dirs` it was constructed with plus the files on disk at run time.
    Together they prove the tree was written whole and torn down after the request.
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
        snapshot["library_dirs_are_callers"] = runner_kwargs.get("library_dirs_are_callers")
        snapshot["methods_dirs"] = methods_dirs
        snapshot["mthds_contents"] = run_kwargs.get("mthds_contents")
        snapshot["pipe_code"] = run_kwargs.get("pipe_code")
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


def _assert_tree_refusal(response: Any, *, code: str, named: str) -> None:
    assert response.status_code == 422, response.text
    problem = response.json()
    assert problem["error_type"] == "InvalidMethodFiles", response.text
    assert problem["tree_refusal"]["code"] == code
    assert named in problem["tree_refusal"]["names"]
    assert repr(named) in problem["detail"] or f"'{named}'" in problem["detail"]


class TestPipelineBundle:
    @pytest.mark.parametrize("transport", ["files", "bundle_b64"])
    @pytest.mark.parametrize("path", ["/v1/execute", "/v1/start"])
    def test_a_method_tree_is_written_whole_as_the_callers_library_dir(self, mocker: MockerFixture, transport: str, path: str):
        """The tree is written as it was sent, its bundles and every other file, and handed over as the caller's own method."""
        client, snapshot = _build_client(mocker)
        files = {"main.mthds": VALID_MTHDS, "notes/readme.txt": "a note"}
        body: dict[str, Any] = {"files": files} if transport == "files" else {"bundle_b64": _zip_b64(files)}

        response = client.post(path, json={**body, "inputs": {"text": "hi"}})

        assert response.status_code in {200, 202}, response.text
        assert snapshot["mthds_contents"] is None
        assert snapshot["files"] == ["main.mthds", "notes/readme.txt"]
        assert snapshot["library_dirs_are_callers"] is True
        assert snapshot["dir_exists"] is True
        # The entry pipe is the one `main_pipe` the bundles declare, qualified by its bundle's domain.
        assert snapshot["pipe_code"] == "smoke.echo"
        assert snapshot["methods_dirs"] is None
        # The tree is removed once the request returns.
        assert not Path(snapshot["library_dirs"][0]).exists()

    def test_a_request_pipe_code_overrides_the_entry_pipe(self, mocker: MockerFixture):
        client, snapshot = _build_client(mocker)
        response = client.post("/v1/execute", json={"files": {"main.mthds": VALID_MTHDS}, "pipe_code": "echo", "inputs": {"text": "hi"}})
        assert response.status_code == 200, response.text
        assert snapshot["pipe_code"] == "echo"

    def test_a_tree_with_no_entry_pipe_and_no_pipe_code_is_refused(self, mocker: MockerFixture):
        client, snapshot = _build_client(mocker)
        files = {"a.mthds": VALID_MTHDS, "b.mthds": VALID_MTHDS.replace('domain = "smoke"', 'domain = "other"')}

        response = client.post("/v1/execute", json={"files": files, "inputs": {"text": "hi"}})

        assert response.status_code == 422, response.text
        problem = response.json()
        assert problem["error_type"] == "MethodEntryError"
        assert "'a.mthds'" in problem["detail"]
        assert "'b.mthds'" in problem["detail"]
        assert snapshot == {}, "the runner was reached"

    def test_no_bundle_passes_request_mthds_contents(self, mocker: MockerFixture):
        client, snapshot = _build_client(mocker)
        response = client.post("/v1/execute", json={"pipe_code": "echo", "mthds_contents": [VALID_MTHDS], "inputs": {}})
        assert response.status_code == 200
        assert snapshot["library_dirs"] is None
        assert snapshot["library_dirs_are_callers"] is False
        assert snapshot["mthds_contents"] == [VALID_MTHDS]

    def test_python_bundle_forbidden_when_not_hosted(self, mocker: MockerFixture):
        mocker.patch(f"{_TREE_NS}.is_pipe_func_sandbox_hosted", return_value=False)
        client, snapshot = _build_client(mocker)
        response = client.post("/v1/execute", json={"files": {"main.mthds": VALID_MTHDS, "funcs/pipe_func.py": _PIPE_FUNC_PY}})
        assert response.status_code == 403
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "CustomCodeRequiresSandbox"
        assert snapshot == {}, "the runner was reached"

    def test_python_bundle_is_written_with_its_tree_when_hosted(self, mocker: MockerFixture):
        mocker.patch(f"{_TREE_NS}.is_pipe_func_sandbox_hosted", return_value=True)
        client, snapshot = _build_client(mocker)
        response = client.post("/v1/execute", json={"files": {"main.mthds": VALID_MTHDS, "funcs/pipe_func.py": _PIPE_FUNC_PY}})
        assert response.status_code == 200, response.text
        assert snapshot["mthds_contents"] is None
        assert snapshot["files"] == ["funcs/pipe_func.py", "main.mthds"]

    def test_both_forms_rejected_via_route(self, mocker: MockerFixture):
        client, _ = _build_client(mocker)
        response = client.post(
            "/v1/execute",
            json={"files": {"main.mthds": VALID_MTHDS}, "bundle_b64": _zip_b64({"main.mthds": VALID_MTHDS})},
        )
        assert response.status_code == 422
        assert response.json()["error_type"] == "InvalidBundle"

    def test_a_tree_holding_no_bundle_is_refused(self, mocker: MockerFixture):
        client, snapshot = _build_client(mocker)
        response = client.post("/v1/execute", json={"files": {"notes.txt": "x"}, "pipe_code": "smoke.echo", "inputs": {}})
        assert response.status_code == 422, response.text
        assert response.json()["error_type"] == "InvalidBundle"
        assert snapshot == {}, "the runner was reached"

    @pytest.mark.parametrize(
        ("files", "code", "named"),
        [
            pytest.param({"main.mthds": VALID_MTHDS, "notes\ud800.txt": "x"}, "invalid_tree_path", r"notes\ud800.txt", id="in-name"),
        ],
    )
    def test_a_files_key_that_is_not_utf8_text_is_refused(self, mocker: MockerFixture, files: dict[str, str], code: str, named: str):
        """A lone surrogate rides JSON as an escape but has no UTF-8 form, so the key is no tree path, never written."""
        client, snapshot = _build_client(mocker)
        # The escaped `\ud800` is valid JSON text, which `json=` would refuse to encode.
        raw_body = json.dumps({"files": files, "inputs": {"text": "hi"}})

        response = client.post("/v1/execute", content=raw_body, headers={"content-type": "application/json"})

        assert response.status_code == 422, response.text
        problem = response.json()
        assert problem["error_type"] == "InvalidMethodFiles"
        assert problem["tree_refusal"] == {"code": code, "names": [named]}
        assert snapshot == {}, "the runner was reached"

    def test_a_text_entry_that_is_not_utf8_text_is_refused(self, mocker: MockerFixture):
        client, snapshot = _build_client(mocker)
        raw_body = json.dumps({"files": {"main.mthds": VALID_MTHDS, "notes.txt": "\ud800"}, "inputs": {"text": "hi"}})

        response = client.post("/v1/execute", content=raw_body, headers={"content-type": "application/json"})

        assert response.status_code == 422, response.text
        problem = response.json()
        assert problem["error_type"] == "InvalidMethodFiles"
        assert problem["tree_refusal"]["names"] == ["notes.txt"]
        assert snapshot == {}, "the runner was reached"

    def test_bundle_and_mthds_contents_are_mutually_exclusive(self, mocker: MockerFixture):
        client, _ = _build_client(mocker)
        response = client.post(
            "/v1/execute",
            json={"files": {"main.mthds": VALID_MTHDS}, "mthds_contents": [VALID_MTHDS]},
        )
        assert response.status_code == 422
        assert "mutually exclusive" in response.text

    @pytest.mark.parametrize("transport", ["dependencies", "bundle_b64"])
    @pytest.mark.parametrize("path", ["/v1/execute", "/v1/start"])
    def test_a_dependency_gets_its_own_methods_dir(self, mocker: MockerFixture, transport: str, path: str):
        """A dependency tree, sent in `dependencies` or shipped in an archive's store, is written into a methods dir of its own."""
        mocker.patch(f"{_TREE_NS}.is_pipe_func_sandbox_hosted", return_value=True)
        client, snapshot = _build_client(mocker)
        body: dict[str, Any]
        if transport == "dependencies":
            body = {
                "files": {"bundle.mthds": UNRESOLVED_PACKAGE_MTHDS, "pipe_func.py": _PIPE_FUNC_PY},
                "dependencies": {VENDORED_PROBE_ADDRESS: _PROBE_TREE},
            }
        else:
            body = {"bundle_b64": _zip_b64({**VENDORED_PROBE_FILES, "pipe_func.py": _PIPE_FUNC_PY})}

        response = client.post(path, json={**body, "inputs": {"text": "hi"}})

        assert response.status_code in {200, 202}, response.text
        # The library dir holds the method's own tree, and nothing of the package.
        assert snapshot["files"] == ["bundle.mthds", "pipe_func.py"]
        # The package is in its own methods dir, laid out as `<name>/…`, a path no walk-up could take for a store.
        (methods_dir,) = snapshot["methods_dirs"]
        assert snapshot["methods_files"] == [["probe/METHODS.toml", "probe/probe.mthds"]]
        assert ".mthds/methods" not in Path(methods_dir).as_posix()
        # Cleaned once the request returns, like the library dir.
        assert not Path(methods_dir).exists()

    def test_a_dependency_keyed_by_another_address_than_its_manifests_is_refused(self, mocker: MockerFixture):
        client, snapshot = _build_client(mocker)
        body = {"files": {"bundle.mthds": UNRESOLVED_PACKAGE_MTHDS}, "dependencies": {"github.com/invented/elsewhere/probe": _PROBE_TREE}}

        response = client.post("/v1/execute", json={**body, "inputs": {"text": "hi"}})

        assert response.status_code == 422, response.text
        problem = response.json()
        assert problem["error_type"] == "InvalidMethodFiles"
        assert VENDORED_PROBE_ADDRESS in problem["detail"]
        assert snapshot == {}, "the runner was reached"

    def test_dependencies_without_files_are_refused(self, mocker: MockerFixture):
        client, snapshot = _build_client(mocker)
        body = {"mthds_contents": [UNRESOLVED_PACKAGE_MTHDS], "dependencies": {VENDORED_PROBE_ADDRESS: _PROBE_TREE}}

        response = client.post("/v1/execute", json={**body, "inputs": {"text": "hi"}})

        assert response.status_code == 422, response.text
        assert response.json()["code"] == "request.invalid"
        assert response.json()["error_type"] == "PipelexRequestError"
        assert "dependencies" in response.json()["detail"]
        assert snapshot == {}, "the runner was reached"

    def test_a_bundle_shipping_no_package_gets_no_methods_dir(self, mocker: MockerFixture):
        client, snapshot = _build_client(mocker)
        response = client.post("/v1/execute", json={"files": {"main.mthds": VALID_MTHDS}, "inputs": {"text": "hi"}})
        assert response.status_code == 200
        assert snapshot["methods_dirs"] is None

    @pytest.mark.parametrize("shape", list(_REFUSED_ARCHIVE_SHAPES))
    def test_a_misplaced_mthds_entry_of_an_archive_is_refused_by_the_tree_rule(self, mocker: MockerFixture, shape: str):
        """An archive entry under a dot directory that is no package of its store is refused by the tree's rule, never dropped."""
        files, named = _REFUSED_ARCHIVE_SHAPES[shape]
        client, snapshot = _build_client(mocker)

        response = client.post("/v1/execute", json={"bundle_b64": _zip_b64(files), "inputs": {"text": "hi"}})

        assert response.status_code == 422, response.text
        problem = response.json()
        assert problem["error_type"] == "InvalidMethodFiles"
        assert named in problem["detail"]
        assert snapshot == {}, "the runner was reached"

    @pytest.mark.parametrize("shape", list(_REFUSED_ARCHIVE_PACKAGES))
    def test_a_shipped_package_with_no_valid_manifest_is_refused(self, mocker: MockerFixture, shape: str):
        files, named = _REFUSED_ARCHIVE_PACKAGES[shape]
        client, snapshot = _build_client(mocker)

        response = client.post("/v1/execute", json={"bundle_b64": _zip_b64(files), "inputs": {"text": "hi"}})

        assert response.status_code == 422, response.text
        problem = response.json()
        assert problem["error_type"] == "InvalidMethodFiles"
        assert named in problem["detail"]
        assert snapshot == {}, "the runner was reached"

    def test_an_archive_whose_only_bundles_are_shipped_packages_is_refused(self, mocker: MockerFixture):
        client, snapshot = _build_client(mocker)
        files = {".mthds/methods/probe/METHODS.toml": VENDORED_PROBE_MANIFEST, ".mthds/methods/probe/probe.mthds": VENDORED_PROBE_MTHDS}

        response = client.post("/v1/execute", json={"bundle_b64": _zip_b64(files), "inputs": {"text": "hi"}})

        assert response.status_code == 422, response.text
        problem = response.json()
        assert problem["error_type"] in {"InvalidBundle", "InvalidMethodFiles"}
        assert snapshot == {}, "the runner was reached"

    @pytest.mark.parametrize("bundle", list(_DUPLICATE_IDENTITY_BUNDLES))
    def test_two_shipped_packages_of_one_identity_are_refused(self, mocker: MockerFixture, bundle: str):
        """Which of two packages a reference would match is no choice to make by directory order: the archive is refused."""
        files = _DUPLICATE_IDENTITY_BUNDLES[bundle]
        client, snapshot = _build_client(mocker)

        response = client.post("/v1/execute", json={"bundle_b64": _zip_b64(files), "inputs": {"text": "hi"}})

        assert response.status_code == 422, response.text
        problem = response.json()
        assert problem["error_type"] == "InvalidMethodFiles"
        assert VENDORED_PROBE_ADDRESS.casefold() in problem["detail"].casefold()
        assert snapshot == {}, "the runner was reached"

    @pytest.mark.parametrize("transport", ["files", "bundle_b64"])
    @pytest.mark.parametrize("case", list(_REFUSED_ENTRIES))
    def test_an_entry_the_tree_rule_refuses_is_refused_naming_it(self, mocker: MockerFixture, transport: str, case: str):
        """A key that is not a tree path, one the membership rule keeps out, or two entries of one path: refused, never written."""
        entries, code, named = _REFUSED_ENTRIES[case]
        if transport == "bundle_b64" and code == "excluded_name" and named.startswith(".mthds/methods/"):
            pytest.skip("An archive ships packages in the local store layout.")
        client, snapshot = _build_client(mocker)
        body: dict[str, Any] = {"files": dict(entries)} if transport == "files" else {"bundle_b64": _zip_b64_of_entries(entries)}

        response = client.post("/v1/execute", json={**body, "inputs": {"text": "hi"}})

        _assert_tree_refusal(response, code=code, named=named)
        assert snapshot == {}, "the runner was reached"

    def test_a_zip_member_named_twice_is_refused(self, mocker: MockerFixture):
        """A zip may hold one member name twice, spelled the same: a duplicate key of the map it is read as."""
        client, snapshot = _build_client(mocker)
        with pytest.warns(UserWarning, match="Duplicate name"):
            bundle_b64 = _zip_b64_of_entries([("main.mthds", VALID_MTHDS), ("notes.txt", "a"), ("notes.txt", "b")])

        response = client.post("/v1/execute", json={"bundle_b64": bundle_b64, "inputs": {"text": "hi"}})

        _assert_tree_refusal(response, code="duplicate_key", named="notes.txt")
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

        response = client.post("/v1/execute", json={"bundle_b64": _zip_b64(files), "inputs": {"text": "hi"}})

        assert response.status_code == 200, response.text
        assert snapshot["methods_files"] == [["probe/METHODS.toml", "probe/probe.mthds"], ["sibling/METHODS.toml", "sibling/probe.mthds"]]
