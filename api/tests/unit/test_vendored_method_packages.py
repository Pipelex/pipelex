"""A request carries the method packages its method calls: as `dependencies` beside `files`, or under `.mthds/methods/<name>/` in an archive.

A fetched package carries them the second way, in its repository. The routes and the runner are real, and so is the
in-process orchestrator of the run tests: what the run answers is what the engine resolved. Fetch-on-miss is off and
the installed store is an empty temporary directory, so the shipped package is the only one that can answer, or, where
a test installs a competing copy, the one that must win. The invented package's entry composes a text naming its copy,
which a dry run renders too, so the output tells which ran.
"""

import base64
import io
import json
import tempfile
import zipfile
from collections.abc import Callable, Generator, Mapping
from pathlib import Path
from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from mthds.protocol.problem.registry import CoreCode
from pipelex.config import get_config
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.plugins.orchestrator_registry import OrchestratorRegistry
from pipelex.runtime_bridge.payloads import PipelexPipeDispatchAck, PipelexPipeRunOutput
from pytest_mock import MockerFixture

from pipelex_api.api_config import ApiConfig
from pipelex_api.errors import ApiError
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.method_source import fetch_method_mthds_files, fetched_method
from pipelex_api.problem_view import mark_operator_request
from pipelex_api.routes import router as api_router
from tests.unit._constants import (
    STUB_METHOD_ADDRESS,
    UNRESOLVED_PACKAGE_MTHDS,
    UNRESOLVED_PACKAGE_REFERENCE,
    VENDORED_PROBE_ADDRESS,
    VENDORED_PROBE_FILES,
    VENDORED_PROBE_MANIFEST,
    VENDORED_PROBE_MARKER,
    VENDORED_PROBE_MTHDS,
)

_PIPELINE_NS = "pipelex_api.routes.pipelex.pipeline"
_METHOD_REF = f"{STUB_METHOD_ADDRESS}@v0.1.0"
_INSTALLED_MARKER = "INSTALLED copy"

# The shipped package's bundle, made unparsable two ways: as TOML, and as a blueprint whose `main_pipe` is no pipe code.
_UNPARSABLE_PROBE_BUNDLES: dict[str, str] = {
    "toml syntax": 'domain = "probe_dep"\n\n[pipe.entry\ntype = "PipeLLM"\n',
    "invalid blueprint": VENDORED_PROBE_MTHDS.replace('domain = "probe_dep"', 'domain = "probe_dep"\nmain_pipe = "Not A Pipe Code!"'),
}


def _structures_py(*, sentinel: Path) -> str:
    """A structure class whose module, if it were ever imported, would write the sentinel file."""
    return f"""\
from pathlib import Path

from pipelex.core.stuffs.structured_content import StructuredContent

Path({str(sentinel)!r}).write_text("imported", encoding="utf-8")


class Invoice(StructuredContent):
    total: float
"""


class _RecordingOrchestrator:
    """An async-capable orchestrator that acknowledges a start and records what each dispatched job's library holds."""

    supports_fire_and_forget = True

    def __init__(self) -> None:
        self.dispatches: list[str] = []

    async def execute(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeRunOutput:  # noqa: ARG002
        msg = "These tests dispatch through /start only."
        raise AssertionError(msg)

    async def start(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeDispatchAck:  # noqa: ARG002
        self.dispatches.append(pipe_job.pipe.code)
        return PipelexPipeDispatchAck(pipeline_run_id="run-1", workflow_id="wf-1")


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


def _build_client(
    mocker: MockerFixture,
    *,
    tmp_path: Path,
    orchestrator: _RecordingOrchestrator | None = None,
    as_operator: bool = False,
) -> TestClient:
    """The routes behind the production handlers; `as_operator` marks each request as the operator's, who reads `diagnostics`."""
    mocker.patch("pipelex.cli.installed_methods.GLOBAL_METHODS_DIR", tmp_path / "global-methods")
    mocker.patch("pipelex.cli.installed_methods.PROJECT_METHODS_DIR", tmp_path / "project-methods")
    mocker.patch("pipelex.methods.fetch_on_miss.is_method_fetch_on_miss_enabled", return_value=False)
    mocker.patch("pipelex.methods.fetch_on_miss.fetch_method_package", side_effect=AssertionError("nothing may be fetched"))
    mocker.patch(
        f"{_PIPELINE_NS}.get_api_config", return_value=ApiConfig(orchestration_mode="direct", allow_request_orchestration_mode_override=False)
    )
    if orchestrator is not None:
        mocker.patch(f"{_PIPELINE_NS}.get_orchestrator_registry", return_value=OrchestratorRegistry({"direct": orchestrator}))
    app = FastAPI()
    app.include_router(api_router, prefix="/v1", dependencies=[Depends(mark_operator_request)] if as_operator else [])
    register_exception_handlers(app)
    return TestClient(app)


def _install_competing_probe(*, tmp_path: Path) -> None:
    """Install the same package into the isolated store, its entry describing itself as the installed copy."""
    package_dir = tmp_path / "global-methods" / "probe"
    package_dir.mkdir(parents=True)
    (package_dir / "METHODS.toml").write_text(VENDORED_PROBE_MANIFEST, encoding="utf-8")
    (package_dir / "probe.mthds").write_text(VENDORED_PROBE_MTHDS.replace(VENDORED_PROBE_MARKER, _INSTALLED_MARKER), encoding="utf-8")


def _run_output(body: dict[str, Any]) -> str:
    """The run's working memory as text, where the composed answer names the copy of the package that ran."""
    return json.dumps(body["pipe_output"]["working_memory"])


_PROBE_PREFIX = ".mthds/methods/probe/"


def _tree_body(files: dict[str, str]) -> dict[str, Any]:
    """The method of the files in the store's layout as a request sends it: its own `files`, and the probe in `dependencies`."""
    own = {tree_path: content for tree_path, content in files.items() if not tree_path.startswith(_PROBE_PREFIX)}
    probe = {tree_path.removeprefix(_PROBE_PREFIX): content for tree_path, content in files.items() if tree_path.startswith(_PROBE_PREFIX)}
    return {"files": own, "dependencies": {VENDORED_PROBE_ADDRESS: probe}}


def _execute_vendored(client: TestClient, *, files: dict[str, str]) -> Any:
    return client.post("/v1/execute", json={**_tree_body(files), "inputs": {"text": "hello"}})


def _zip_b64(files: Mapping[str, str | bytes]) -> str:
    """A `bundle_b64` of the files, which, unlike a `files` map, can carry bytes that are not text."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class TestVendoredMethodPackages:
    def test_a_shipped_package_answers_the_call_with_fetching_off(self, mocker: MockerFixture, tmp_path: Path):
        client = _build_client(mocker, tmp_path=tmp_path)

        response = _execute_vendored(client, files=VENDORED_PROBE_FILES)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["state"] == "COMPLETED"
        assert f"{VENDORED_PROBE_MARKER}: hello" in _run_output(body)
        # The package ends with the request: nothing was installed into the store.
        assert not (tmp_path / "global-methods").exists()

    def test_the_shipped_copy_wins_over_an_installed_one(self, mocker: MockerFixture, tmp_path: Path):
        client = _build_client(mocker, tmp_path=tmp_path)
        _install_competing_probe(tmp_path=tmp_path)

        response = _execute_vendored(client, files=VENDORED_PROBE_FILES)

        assert response.status_code == 200, response.text
        run_output = _run_output(response.json())
        assert f"{VENDORED_PROBE_MARKER}: hello" in run_output
        assert _INSTALLED_MARKER not in run_output

    def test_a_shipped_provenance_sidecar_that_is_not_utf8_is_ignored(self, mocker: MockerFixture, tmp_path: Path):
        """A sidecar the server cannot read records no provenance, as an unparsable one does, and the shipped copy runs."""
        client = _build_client(mocker, tmp_path=tmp_path)
        bundle_b64 = _zip_b64({**VENDORED_PROBE_FILES, ".mthds/methods/probe/.provenance.json": b"\xff\xfe garbage"})

        response = client.post("/v1/execute", json={"bundle_b64": bundle_b64, "inputs": {"text": "hello"}})

        assert response.status_code == 200, response.text
        assert f"{VENDORED_PROBE_MARKER}: hello" in _run_output(response.json())

    def test_start_hands_the_job_a_library_holding_the_shipped_package(self, mocker: MockerFixture, tmp_path: Path):
        orchestrator = _RecordingOrchestrator()
        client = _build_client(mocker, tmp_path=tmp_path, orchestrator=orchestrator)

        response = client.post("/v1/start", json={**_tree_body(VENDORED_PROBE_FILES), "inputs": {"text": "hello"}})

        assert response.status_code == 202, response.text
        assert orchestrator.dispatches == ["echo"]

    @pytest.mark.parametrize("broken", list(_UNPARSABLE_PROBE_BUNDLES))
    def test_a_shipped_bundle_that_does_not_parse_is_the_verdict(self, mocker: MockerFixture, tmp_path: Path, broken: str):
        """The package is the caller's own content, so its parse failure is the verdict, located by address, never by host path."""
        client = _build_client(mocker, tmp_path=tmp_path)
        files = {**VENDORED_PROBE_FILES, ".mthds/methods/probe/probe.mthds": _UNPARSABLE_PROBE_BUNDLES[broken]}

        response = _execute_vendored(client, files=files)

        assert response.status_code == 422, response.text
        body = response.json()
        assert body["code"] == CoreCode.METHOD_INVALID
        assert body["domain"] == "method"
        items = body["errors"]
        assert items, body
        # Each fault is located in the package by its address, the way the caller's tree names it.
        assert {item["location"]["file"] for item in items} == {f"{VENDORED_PROBE_ADDRESS}/probe.mthds"}
        assert "diagnostics" not in body
        dump = json.dumps(body)
        assert "pipelex-methods-" not in dump
        for temporary_root in (tempfile.gettempdir(), str(Path(tempfile.gettempdir()).resolve())):
            assert temporary_root not in dump

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_a_shipped_structure_class_is_refused_unimported(self, mocker: MockerFixture, tmp_path: Path):
        sentinel = tmp_path / "structures-module-ran"
        orchestrator = _RecordingOrchestrator()
        client = _build_client(mocker, tmp_path=tmp_path, orchestrator=orchestrator, as_operator=True)
        files = {**VENDORED_PROBE_FILES, ".mthds/methods/probe/structures.py": _structures_py(sentinel=sentinel)}

        response = client.post("/v1/start", json={**_tree_body(files), "inputs": {"text": "hello"}})

        assert response.status_code == 422, response.text
        body = response.json()
        assert body["code"] == PipelexErrorCode.DEPLOYMENT_PYTHON_STRUCTURES_REFUSED
        # The caller reads the file by the name its tree gives a shipped package's file: the address, then the path inside.
        assert body.get("params") == {"files": [f"{VENDORED_PROBE_ADDRESS}/structures.py"]}
        # Named as the fetched package's refusal is: by the package's address, and the file by its path inside it.
        assert body["diagnostics"]["error_class"] == "MethodStructuresRefusedError"
        assert f"Method package '{VENDORED_PROBE_ADDRESS}'" in body["diagnostics"]["message"]
        assert "structures.py defines Invoice" in body["diagnostics"]["message"]
        assert not sentinel.exists(), "the structure module was imported"
        assert orchestrator.dispatches == []

    def test_a_method_ref_package_runs_the_dependency_it_ships(
        self, mocker: MockerFixture, tmp_path: Path, install_method_package: Callable[..., Path]
    ):
        install_method_package(files={"smoke.mthds": UNRESOLVED_PACKAGE_MTHDS, **_package_vendoring_files()})
        client = _build_client(mocker, tmp_path=tmp_path)

        response = client.post("/v1/execute", json={"method_ref": _METHOD_REF, "inputs": {"text": "hello"}})

        assert response.status_code == 200, response.text
        assert f"{VENDORED_PROBE_MARKER}: hello" in _run_output(response.json())

    def test_a_method_ref_package_shipping_one_identity_twice_is_refused(
        self, mocker: MockerFixture, tmp_path: Path, install_method_package: Callable[..., Path]
    ):
        shipped_twice = {
            f".mthds/methods/{directory}/{relpath.removeprefix('.mthds/methods/probe/')}": content
            for directory in ("a", "b")
            for relpath, content in _package_vendoring_files().items()
        }
        install_method_package(files={"smoke.mthds": UNRESOLVED_PACKAGE_MTHDS, **shipped_twice})
        client = _build_client(mocker, tmp_path=tmp_path)

        response = client.post("/v1/execute", json={"method_ref": _METHOD_REF, "inputs": {"text": "hello"}})

        assert response.status_code == 422, response.text
        body = response.json()
        assert body["error_type"] == "InvalidMethodFiles"
        assert f"method package '{STUB_METHOD_ADDRESS}'" in body["detail"]
        assert VENDORED_PROBE_ADDRESS in body["detail"]
        assert "'.mthds/methods/b/'" in body["detail"]

    def test_a_method_ref_package_keeps_its_shipped_files_apart(self, install_method_package: Callable[..., Path]):
        install_method_package(files={"smoke.mthds": UNRESOLVED_PACKAGE_MTHDS, **_package_vendoring_files()})

        fetched = fetched_method(_METHOD_REF)

        assert sorted(fetched.request_method.tree.contents) == ["METHODS.toml", "smoke.mthds"]
        assert list(fetched.request_method.dependencies) == [VENDORED_PROBE_ADDRESS]
        assert sorted(fetched.request_method.dependencies[VENDORED_PROBE_ADDRESS].contents) == ["METHODS.toml", "probe.mthds"]
        assert fetched.provenance.tree_digest == fetched.request_method.tree.tree.digest

        tooling = fetch_method_mthds_files(_METHOD_REF)
        assert [item.source for item in tooling.files] == ["smoke.mthds"]

    def test_a_dot_directory_under_the_shipped_packages_is_no_package_of_a_method_ref(self, install_method_package: Callable[..., Path]):
        """A fetched package and an archive hold `.mthds/methods/<name>/` to one rule: a dot directory there is no package.

        A copy of the probe under `.mthds/methods/.cache/` would otherwise declare the probe's identity a second time.
        """
        hidden_copy = {
            f".mthds/methods/.cache/{relpath.removeprefix('.mthds/methods/probe/')}": content
            for relpath, content in _package_vendoring_files().items()
        }
        install_method_package(files={"smoke.mthds": UNRESOLVED_PACKAGE_MTHDS, **_package_vendoring_files(), **hidden_copy})

        fetched = fetched_method(_METHOD_REF)

        assert list(fetched.request_method.dependencies) == [VENDORED_PROBE_ADDRESS]

    def test_the_tooling_read_keeps_the_tree_s_bundles_alone(self, install_method_package: Callable[..., Path]):
        """The tooling routes read the `.mthds` files the tree keeps, without the shipped packages a run needs whole."""
        no_manifest = {".mthds/methods/unfinished/draft.mthds": UNRESOLVED_PACKAGE_MTHDS}
        install_method_package(
            files={
                "smoke.mthds": UNRESOLVED_PACKAGE_MTHDS,
                "ignored/old.mthds": UNRESOLVED_PACKAGE_MTHDS,
                ".gitignore": "ignored/\n",
                "notes/readme.txt": "Not read by the tooling routes",
                **no_manifest,
            }
        )

        tooling = fetch_method_mthds_files(_METHOD_REF)

        assert [item.source for item in tooling.files] == ["smoke.mthds"]
        assert tooling.main_pipe == "echo"
        with pytest.raises(ApiError, match="unfinished"):
            fetched_method(_METHOD_REF)

    def test_validate_by_method_ref_resolves_the_dependency_it_ships(
        self, mocker: MockerFixture, tmp_path: Path, install_method_package: Callable[..., Path]
    ):
        """`/v1/validate` loads the package's tree with the dependency it ships, as a run does, and echoes its own bundles only."""
        install_method_package(files={"smoke.mthds": UNRESOLVED_PACKAGE_MTHDS, **_package_vendoring_files()})
        client = _build_client(mocker, tmp_path=tmp_path)

        response = client.post("/v1/validate", json={"method_ref": _METHOD_REF})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True, body
        assert body["mthds_contents"] == [UNRESOLVED_PACKAGE_MTHDS]

    def test_validate_by_method_ref_without_the_dependency_is_an_invalid_verdict(
        self, mocker: MockerFixture, tmp_path: Path, install_method_package: Callable[..., Path]
    ):
        install_method_package(files={"smoke.mthds": UNRESOLVED_PACKAGE_MTHDS})
        client = _build_client(mocker, tmp_path=tmp_path)

        response = client.post("/v1/validate", json={"method_ref": _METHOD_REF})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        assert [(item["error_type"], item["missing_pipe_code"]) for item in body["validation_errors"]] == [
            ("unresolved_package_dependency", UNRESOLVED_PACKAGE_REFERENCE)
        ]


def _package_vendoring_files() -> dict[str, str]:
    """The shipped package's files, without the consumer's bundle `VENDORED_PROBE_FILES` also holds."""
    return {relpath: content for relpath, content in VENDORED_PROBE_FILES.items() if relpath.startswith(".mthds/")}
