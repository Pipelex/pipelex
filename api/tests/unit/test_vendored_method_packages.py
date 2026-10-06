"""A request carries the method packages its bundle calls, under `.mthds/methods/<name>/` at the bundle's root.

The routes and the runner are real, and so is the in-process orchestrator of the run tests: what the run answers is
what the engine resolved. Fetch-on-miss is off and the installed store is an empty temporary directory, so the shipped
package is the only one that can answer, or, where a test installs a competing copy, the one that must win. The
invented package's entry composes a text naming its copy, which a dry run renders too, so the output tells which ran.
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
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipelex.base_exceptions import DisclosureMode
from pipelex.config import get_config
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.plugins.orchestrator_registry import OrchestratorRegistry
from pipelex.runtime_bridge.payloads import PipelexPipeDispatchAck, PipelexPipeRunOutput
from pytest_mock import MockerFixture

from pipelex_api.api_config import ApiConfig
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.method_source import fetch_method_mthds_files, fetched_method_source
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
    disclosure_mode: DisclosureMode = DisclosureMode.STRICT,
) -> TestClient:
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
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app, disclosure_mode=disclosure_mode)
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


def _execute_vendored(client: TestClient, *, files: dict[str, str]) -> Any:
    return client.post("/v1/execute", json={"files": files, "inputs": {"text": "hello"}})


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

        response = client.post("/v1/start", json={"files": VENDORED_PROBE_FILES, "inputs": {"text": "hello"}})

        assert response.status_code == 202, response.text
        assert orchestrator.dispatches == ["echo"]

    @pytest.mark.parametrize("broken", list(_UNPARSABLE_PROBE_BUNDLES))
    def test_a_shipped_bundle_that_does_not_parse_is_the_verdict(self, mocker: MockerFixture, tmp_path: Path, broken: str):
        """The package is the caller's own content, so its parse failure is the verdict, located by address, never by host path."""
        client = _build_client(mocker, tmp_path=tmp_path, disclosure_mode=DisclosureMode.STRICT)
        files = {**VENDORED_PROBE_FILES, ".mthds/methods/probe/probe.mthds": _UNPARSABLE_PROBE_BUNDLES[broken]}

        response = _execute_vendored(client, files=files)

        assert response.status_code == 422, response.text
        body = response.json()
        assert body["error_type"] == "ValidateBundleError"
        items = body["validation_errors"]
        assert items, body
        assert {item["source"] for item in items} == {f"{VENDORED_PROBE_ADDRESS}/probe.mthds"}
        assert VENDORED_PROBE_ADDRESS in body["detail"]
        dump = json.dumps(body)
        assert "pipelex-methods-" not in dump
        for temporary_root in (tempfile.gettempdir(), str(Path(tempfile.gettempdir()).resolve())):
            assert temporary_root not in dump

    @pytest.mark.usefixtures("sandbox_hosted_mode")
    def test_a_shipped_structure_class_is_refused_unimported(self, mocker: MockerFixture, tmp_path: Path):
        sentinel = tmp_path / "structures-module-ran"
        orchestrator = _RecordingOrchestrator()
        client = _build_client(mocker, tmp_path=tmp_path, orchestrator=orchestrator)
        files = {**VENDORED_PROBE_FILES, ".mthds/methods/probe/structures.py": _structures_py(sentinel=sentinel)}

        response = client.post("/v1/start", json={"files": files, "inputs": {"text": "hello"}})

        assert response.status_code == 403, response.text
        body = response.json()
        assert body["error_type"] == "MethodStructuresRefusedError"
        # Named as the fetched package's refusal is: by the package's address, and the file by its path inside it.
        assert f"Method package '{VENDORED_PROBE_ADDRESS}'" in body["detail"]
        assert "structures.py defines Invoice" in body["detail"]
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
        assert body["error_type"] == "InvalidBundle"
        assert f"Method package '{STUB_METHOD_ADDRESS}'" in body["detail"]
        assert VENDORED_PROBE_ADDRESS in body["detail"]
        assert "'.mthds/methods/a/'" in body["detail"]
        assert "'.mthds/methods/b/'" in body["detail"]

    def test_a_method_ref_package_keeps_its_shipped_files_apart(self, install_method_package: Callable[..., Path]):
        install_method_package(files={"smoke.mthds": UNRESOLVED_PACKAGE_MTHDS, **_package_vendoring_files()})

        with fetched_method_source(_METHOD_REF) as fetched:
            assert fetched.mthds_sources == ["smoke.mthds"]
            assert fetched.mthds_contents == [UNRESOLVED_PACKAGE_MTHDS]
            assert fetched.library_dirs is None
            assert fetched.methods_dirs is not None
            (methods_dir,) = fetched.methods_dirs
            assert sorted(path.relative_to(methods_dir).as_posix() for path in methods_dir.rglob("*") if path.is_file()) == [
                "probe/METHODS.toml",
                "probe/probe.mthds",
            ]
        assert not methods_dir.exists()

        tooling = fetch_method_mthds_files(_METHOD_REF)
        assert [item.source for item in tooling.files] == ["smoke.mthds"]

    def test_validate_by_method_ref_validates_only_the_package_s_own_content(
        self, mocker: MockerFixture, tmp_path: Path, install_method_package: Callable[..., Path]
    ):
        """`/v1/validate` leaves a shipped package out of the content; the dependency resolves from the installed store there."""
        install_method_package(files={"smoke.mthds": UNRESOLVED_PACKAGE_MTHDS, **_package_vendoring_files()})
        client = _build_client(mocker, tmp_path=tmp_path)
        _install_competing_probe(tmp_path=tmp_path)

        response = client.post("/v1/validate", json={"method_ref": _METHOD_REF})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True, body
        assert body["mthds_contents"] == [UNRESOLVED_PACKAGE_MTHDS]

    def test_validate_by_method_ref_does_not_search_the_shipped_package(
        self, mocker: MockerFixture, tmp_path: Path, install_method_package: Callable[..., Path]
    ):
        install_method_package(files={"smoke.mthds": UNRESOLVED_PACKAGE_MTHDS, **_package_vendoring_files()})
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
