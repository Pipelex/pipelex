"""The `resources` a request submits beside its `mthds_contents`: the files its steps read, keyed by the path a step names.

Pins the wire across the routes that load inline contents: the files reach the step that reads them, a file no step
names is refused as the request's fault, a path that cannot name a file inside the bundle is refused, and the count,
per-file and total limits are enforced before anything loads. Beside a method tree, which the crate routes take alone,
the files join the tree instead. A run handed to an orchestrator other than `direct` names
the tree of the submitted files by its digest, in its crate and its run metadata, and carries none of their bytes.

The hermetic API environment has no document engine, so the step's engine is stubbed and the dry print's template check
records the bytes it reads through the method file store, which is the read the engine's checker would be handed.
"""

import asyncio
import base64
import io
import json
import zipfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mthds.method_tree.digest import digest_of_contents, sha256_hex, tree_files_from_contents, tree_listing
from pipelex.cogt.content_generation.assignment_models import RenderDocumentAssignment
from pipelex.cogt.doc_gen.doc_gen_setting import DocGenSetting
from pipelex.core.method_trees.exceptions import MethodFileUnavailableError
from pipelex.core.method_trees.method_files import StoredTree, read_method_file, read_stored_trees
from pipelex.pipe_operators.doc_gen.pipe_doc_gen import PipeDocGen
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.plugins.orchestrator_registry import OrchestratorRegistry
from pipelex.runtime_bridge.payloads import PipelexPipeDispatchAck, PipelexPipeRunOutput
from pytest_mock import MockerFixture

from pipelex_api.api_config import ApiConfig
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router
from tests.unit._constants import STUB_METHOD_ADDRESS

_PIPELINE_NS = "pipelex_api.routes.pipelex.pipeline"
_RESOURCES_NS = "pipelex_api.bundle_resources"
_PRINT_STAGE_NS = "pipelex.cogt.content_generation.doc_gen_generate"

_TEMPLATE_PATH = "templates/invoice.docx"
_TEMPLATE_BYTES = b"PK\x03\x04 a docx template"

_INVOICE_MTHDS = f"""
domain = "invoicing"
description = "Printing an invoice"
main_pipe = "print_invoice"

[concept.Invoice]
description = "An invoice to print"

[concept.Invoice.structure]
number = {{ type = "text", description = "The invoice number", required = true }}

[concept.InvoiceFile]
description = "The invoice as a file"
refines     = "Document"

[pipe.print_invoice]
type          = "PipeDocGen"
description   = "Print the invoice in Word"
inputs        = {{ invoice = "Invoice" }}
output        = "InvoiceFile"
format        = "docx"
template_file = "{_TEMPLATE_PATH}"
"""

_INVOICE_INPUTS: dict[str, Any] = {"invoice": {"concept": "invoicing.Invoice", "content": {"number": "INV-1"}}}

# The stub package's manifest, starting the method at the invoice's print.
_INVOICE_PACKAGE_MANIFEST = """\
[package]
name = "documents"
address = "github.com/pipelex/methods"
version = "0.1.0"
description = "A stub package printing an invoice from the template it ships."
main_pipe = "print_invoice"

[exports.invoicing]
pipes = ["print_invoice"]
"""


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


def _stub_the_document_engine(mocker: MockerFixture) -> list[bytes]:
    """Resolve every PipeDocGen step to an engine, and record the template bytes each dry print's check reads for its step.

    The dry print reads the step's template file through the method file store, which serves the tree of the files sent
    with the bundle while the run's library holds it.
    """
    read_templates: list[bytes] = []

    async def _record_template_check(*, render_assignment: RenderDocumentAssignment) -> None:
        template_file = render_assignment.composition.template_file
        assert template_file is not None
        read_templates.append(await read_method_file(file_ref=template_file.file, read_scope=render_assignment.job_metadata.run_metadata.read_scope))

    mocker.patch.object(PipeDocGen, "resolve_engine", return_value=DocGenSetting(model="stub-docx"))
    mocker.patch(f"{_PRINT_STAGE_NS}._check_template_file", side_effect=_record_template_check)
    return read_templates


class _RecordingTemporalStub:
    """An async-capable orchestrator standing in for Temporal: it records the job it is handed, copies its trees and acks it.

    It copies every tree the job's crate names while it starts, as an orchestrator running the job out of process must
    before it returns, since the runner may drop the files and the library holding them as soon as it does.
    """

    supports_fire_and_forget = True

    def __init__(self) -> None:
        self.pipe_jobs: list[PipeJob] = []
        self.copied_trees: list[StoredTree] = []

    async def execute(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeRunOutput:
        msg = "/start drives the fire-and-forget `start` arm; `execute` must not be reached."
        raise NotImplementedError(msg)

    async def start(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeDispatchAck:  # noqa: ARG002
        self.pipe_jobs.append(pipe_job)
        crate = pipe_job.library_crate
        assert crate is not None
        self.copied_trees.extend(await read_stored_trees(tree_digests=crate.tree_digests(), read_scope=pipe_job.job_metadata.run_metadata.read_scope))
        return PipelexPipeDispatchAck(pipeline_run_id=pipe_job.job_metadata.run_metadata.pipeline_run_id, workflow_id="wf-1")


def _record_dispatches_to_a_temporal_like_orchestrator(mocker: MockerFixture) -> _RecordingTemporalStub:
    """Make Temporal the deployment's orchestrator, recording each job it is handed."""
    mocker.patch(
        f"{_PIPELINE_NS}.get_api_config", return_value=ApiConfig(orchestration_mode="temporal", allow_request_orchestration_mode_override=False)
    )
    orchestrator = _RecordingTemporalStub()
    mocker.patch(f"{_PIPELINE_NS}.get_orchestrator_registry", return_value=OrchestratorRegistry({"temporal": orchestrator}))
    return orchestrator


def _assert_the_job_names_the_tree_of(*, pipe_job: PipeJob, files: Mapping[str, bytes], pipe_ref: str = "invoicing.print_invoice") -> None:
    """The job's crate and run metadata name the tree of these files by digest, and the job carries none of their bytes."""
    crate = pipe_job.library_crate
    assert crate is not None
    tree_digest = digest_of_contents(dict(files))
    assert crate.tree_bundles[pipe_ref].tree_digest == tree_digest
    run_metadata = pipe_job.job_metadata.run_metadata
    assert run_metadata.method_tree_digest == tree_digest
    assert run_metadata.crate_fingerprint == crate.fingerprint
    job_json = pipe_job.model_dump_json()
    for data in files.values():
        assert _b64(data) not in job_json


def _assert_the_orchestrator_copied_the_tree_of(*, orchestrator: _RecordingTemporalStub, files: Mapping[str, bytes]) -> None:
    """The orchestrator read the tree of these files, its listing and each of its files, while it started."""
    (copied_tree,) = orchestrator.copied_trees
    assert copied_tree.tree_digest == digest_of_contents(dict(files))
    assert copied_tree.listing == tree_listing(tree_files_from_contents(dict(files)))
    assert copied_tree.blobs == {sha256_hex(data): data for data in files.values()}


def _zip_b64(files: Mapping[str, str | bytes]) -> str:
    """A `bundle_b64` of the files, which, unlike a `files` map, can carry bytes that are not text."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _contents_body(*, route: str, resources: dict[str, str], mthds: str = _INVOICE_MTHDS) -> dict[str, Any]:
    """The route's body carrying the bundle with the given resources: inline where the route takes contents, else as a tree."""
    match route:
        case "/v1/validate":
            return {"mthds_contents": [mthds], "resources": resources}
        case "/v1/execute":
            return {"mthds_contents": [mthds], "inputs": _INVOICE_INPUTS, "resources": resources}
        case "/v1/codegen":
            return {"files": {"invoicing.mthds": mthds}, "kind": "types", "target": "ts-zod", "resources": resources}
        case _:
            return {"files": {"invoicing.mthds": mthds}, "resources": resources}


def _assert_problem(response: Any, *, status: int, error_type: str) -> str:
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    problem = response.json()
    assert problem["error_type"] == error_type, response.text
    assert "is_valid" not in problem
    detail: str = problem["detail"]
    return detail


class TestBundleResourcesRoutes:
    def test_validate_hands_the_step_the_submitted_template_file(self, mocker: MockerFixture) -> None:
        """The validation's dry run reads the template from the submitted bytes, keyed by the path the step names."""
        read_templates = _stub_the_document_engine(mocker)

        response = _build_client().post(
            "/v1/validate",
            json={"mthds_contents": [_INVOICE_MTHDS], "resources": {f"./{_TEMPLATE_PATH}": _b64(_TEMPLATE_BYTES)}},
        )

        assert response.status_code == 200, response.text
        assert response.json()["is_valid"] is True, response.text
        # The validation dry-runs the step for its verdict and again for the graph it draws: every read is the submitted file.
        assert read_templates
        assert set(read_templates) == {_TEMPLATE_BYTES}

    def test_validate_without_the_template_file_is_an_invalid_verdict_saying_it_was_not_supplied(self, mocker: MockerFixture) -> None:
        _stub_the_document_engine(mocker)

        response = _build_client().post("/v1/validate", json={"mthds_contents": [_INVOICE_MTHDS]})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        assert "which was not supplied with its bundle" in str(body["validation_errors"])

    @pytest.mark.parametrize("route", ["/v1/validate", "/v1/execute"])
    def test_a_file_no_step_names_is_refused_on_every_route_that_loads_contents(self, mocker: MockerFixture, route: str) -> None:
        _stub_the_document_engine(mocker)
        body = _contents_body(route=route, resources={_TEMPLATE_PATH: _b64(_TEMPLATE_BYTES), "templates/logo.png": _b64(b"png")})

        response = _build_client().post(route, json=body)
        detail = _assert_problem(response, status=422, error_type="BundleResourceNotNamedError")

        assert "'templates/logo.png'" in detail
        # A deterministic refusal of what the caller sent, as InvalidResourcePath is: the same request fails again.
        assert response.json()["retryable"] is False

    @pytest.mark.parametrize(
        ("path", "reason"),
        [
            ("/etc/invoice.docx", "absolute"),
            ("../invoice.docx", "'..' segment"),
            ("templates\\invoice.docx", "backslash"),
            ("C:invoice.docx", "colon"),
        ],
    )
    def test_a_path_that_cannot_name_a_file_inside_the_bundle_is_refused(self, path: str, reason: str) -> None:
        response = _build_client().post("/v1/validate", json={"mthds_contents": [_INVOICE_MTHDS], "resources": {path: _b64(_TEMPLATE_BYTES)}})

        assert reason in _assert_problem(response, status=422, error_type="InvalidResourcePath")

    @pytest.mark.parametrize("second_value", [pytest.param(_b64(b"b"), id="both_base64"), pytest.param("not base64!", id="second_not_base64")])
    def test_two_spellings_of_one_file_are_refused_before_either_is_decoded(self, second_value: str) -> None:
        response = _build_client().post(
            "/v1/validate",
            json={"mthds_contents": [_INVOICE_MTHDS], "resources": {_TEMPLATE_PATH: _b64(b"a"), f"./{_TEMPLATE_PATH}": second_value}},
        )

        assert "name the same file" in _assert_problem(response, status=422, error_type="InvalidResourcePath")

    def test_a_value_that_is_not_base64_is_refused(self) -> None:
        response = _build_client().post("/v1/validate", json={"mthds_contents": [_INVOICE_MTHDS], "resources": {_TEMPLATE_PATH: "not base64!"}})

        _assert_problem(response, status=400, error_type="InvalidBase64")

    @pytest.mark.parametrize(
        ("limit_patches", "resources", "expected"),
        [
            pytest.param({"MAX_RESOURCES_PER_REQUEST": 1}, {"a.docx": _b64(b"a"), "b.docx": _b64(b"b")}, "1-file limit", id="count"),
            pytest.param({"MAX_RESOURCE_FILE_BYTES": 2048, "_MAX_RESOURCE_B64_CHARS": 1024}, {"a.docx": _b64(bytes(1000))}, "per-file", id="encoded"),
            pytest.param({"MAX_RESOURCE_FILE_BYTES": 1024}, {"a.docx": _b64(bytes(1025))}, "per-file", id="decoded"),
            pytest.param({"MAX_RESOURCES_TOTAL_BYTES": 1024}, {"a.docx": _b64(bytes(600)), "b.docx": _b64(bytes(600))}, "total-size", id="total"),
        ],
    )
    def test_the_limits_are_enforced_before_the_bundle_loads(
        self, mocker: MockerFixture, limit_patches: dict[str, int], resources: dict[str, str], expected: str
    ) -> None:
        for name, value in limit_patches.items():
            mocker.patch(f"{_RESOURCES_NS}.{name}", value)

        response = _build_client().post("/v1/validate", json={"mthds_contents": [_INVOICE_MTHDS], "resources": resources})

        assert expected in _assert_problem(response, status=413, error_type="PayloadTooLarge")

    @pytest.mark.parametrize("route", ["/v1/validate", "/v1/execute", "/v1/pipe-io", "/v1/resolve", "/v1/codegen"])
    def test_resources_beside_a_method_ref_are_refused(self, route: str) -> None:
        """A published method's files are its package's own, so a caller cannot submit them beside its reference."""
        body = _contents_body(route=route, resources={_TEMPLATE_PATH: _b64(_TEMPLATE_BYTES)})
        body.pop("mthds_contents", None)
        body.pop("files", None)
        body["method_ref"] = f"{STUB_METHOD_ADDRESS}@v0.1.0"
        # The run route refuses it in its request model, as the runtime's `request.invalid`; the crate
        # routes refuse it themselves, with the API-authored `ValidationError`.
        expected_error_type = "PipelexRequestError" if route == "/v1/execute" else "ValidationError"

        detail = _assert_problem(_build_client().post(route, json=body), status=422, error_type=expected_error_type)

        assert "method_ref" in detail

    def test_a_source_label_naming_a_file_on_the_runner_never_reads_beside_it(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A caller's absolute source naming a real bundle file, with the template file beside it, reaches nothing on the runner's disk."""
        read_templates = _stub_the_document_engine(mocker)
        bundle_path = tmp_path / "invoicing.mthds"
        bundle_path.write_text(_INVOICE_MTHDS, encoding="utf-8")
        (tmp_path / "templates").mkdir()
        (tmp_path / "templates" / "invoice.docx").write_bytes(_TEMPLATE_BYTES)
        body: dict[str, Any] = {"mthds_contents": [_INVOICE_MTHDS], "mthds_sources": [str(bundle_path)]}

        response = _build_client().post("/v1/validate", json=body)

        assert response.status_code == 200, response.text
        verdict = response.json()
        assert verdict["is_valid"] is False
        assert "which was not supplied with its bundle" in str(verdict["validation_errors"])
        assert read_templates == []

    @pytest.mark.parametrize("route", ["/v1/pipe-io", "/v1/resolve", "/v1/codegen"])
    @pytest.mark.parametrize("sends_the_template", [True, False])
    def test_resources_join_the_tree_a_crate_route_reads(self, mocker: MockerFixture, route: str, sends_the_template: bool) -> None:
        """Beside a tree, `resources` are files of it: the step's template is found there, and a file no step names is kept."""
        _stub_the_document_engine(mocker)
        resources = {"notes/readme.txt": _b64(b"kept beside the method")}
        if sends_the_template:
            resources[_TEMPLATE_PATH] = _b64(_TEMPLATE_BYTES)

        response = _build_client().post(route, json=_contents_body(route=route, resources=resources))

        assert response.status_code == 200, response.text
        verdict = response.json()
        assert verdict["is_valid"] is sends_the_template, response.text
        if not sends_the_template:
            assert _TEMPLATE_PATH in json.dumps(verdict["validation_errors"])

    def test_resources_with_no_bundle_to_read_them_are_refused(self) -> None:
        response = _build_client().post("/v1/execute", json={"pipe_code": "print_invoice", "resources": {_TEMPLATE_PATH: _b64(_TEMPLATE_BYTES)}})

        assert "resources accompany the bundle" in _assert_problem(response, status=422, error_type="PipelexRequestError")
        assert response.json()["code"] == "request.invalid"

    def test_a_run_handed_to_a_remote_orchestrator_names_the_tree_of_its_files_by_digest(self, mocker: MockerFixture) -> None:
        """`/start` on a Temporal-like orchestrator: the job's crate and run metadata name the tree, and the job carries none of its files."""
        _stub_the_document_engine(mocker)
        orchestrator = _record_dispatches_to_a_temporal_like_orchestrator(mocker)

        response = _build_client().post(
            "/v1/start",
            json={"mthds_contents": [_INVOICE_MTHDS], "inputs": _INVOICE_INPUTS, "resources": {_TEMPLATE_PATH: _b64(_TEMPLATE_BYTES)}},
        )

        assert response.status_code == 202, response.text
        (pipe_job,) = orchestrator.pipe_jobs
        _assert_the_job_names_the_tree_of(pipe_job=pipe_job, files={_TEMPLATE_PATH: _TEMPLATE_BYTES})
        _assert_the_orchestrator_copied_the_tree_of(orchestrator=orchestrator, files={_TEMPLATE_PATH: _TEMPLATE_BYTES})

    @pytest.mark.parametrize(
        ("bundle_files", "resources", "tree_files"),
        [
            pytest.param(
                {"invoicing.mthds": _INVOICE_MTHDS, _TEMPLATE_PATH: _TEMPLATE_BYTES},
                None,
                {"invoicing.mthds": _INVOICE_MTHDS.encode("utf-8"), _TEMPLATE_PATH: _TEMPLATE_BYTES},
                id="beside_the_bundle",
            ),
            # The archive is the method's tree: the bundle's step names its file from the bundle's own tree path.
            pytest.param(
                {"methods/invoicing.mthds": _INVOICE_MTHDS, f"methods/{_TEMPLATE_PATH}": _TEMPLATE_BYTES},
                None,
                {"methods/invoicing.mthds": _INVOICE_MTHDS.encode("utf-8"), f"methods/{_TEMPLATE_PATH}": _TEMPLATE_BYTES},
                id="in_a_directory",
            ),
            pytest.param(
                {"invoicing.mthds": _INVOICE_MTHDS, _TEMPLATE_PATH: _TEMPLATE_BYTES},
                {_TEMPLATE_PATH: _b64(_TEMPLATE_BYTES)},
                {"invoicing.mthds": _INVOICE_MTHDS.encode("utf-8"), _TEMPLATE_PATH: _TEMPLATE_BYTES},
                id="also_in_resources",
            ),
        ],
    )
    def test_a_method_bundle_carries_the_office_template_it_ships_to_its_step(
        self, mocker: MockerFixture, bundle_files: dict[str, str | bytes], resources: dict[str, str] | None, tree_files: dict[str, bytes]
    ) -> None:
        """A method sent as an archive is a method tree: the job names that tree, its bundle and the template it ships, by its digest."""
        _stub_the_document_engine(mocker)
        orchestrator = _record_dispatches_to_a_temporal_like_orchestrator(mocker)
        body: dict[str, Any] = {"bundle_b64": _zip_b64(bundle_files), "inputs": _INVOICE_INPUTS}
        if resources is not None:
            body["resources"] = resources

        response = _build_client().post("/v1/start", json=body)

        assert response.status_code == 202, response.text
        (pipe_job,) = orchestrator.pipe_jobs
        _assert_the_job_names_the_tree_of(pipe_job=pipe_job, files=tree_files)
        _assert_the_orchestrator_copied_the_tree_of(orchestrator=orchestrator, files=tree_files)

    def test_a_method_bundle_s_files_map_names_the_html_template_it_ships_by_its_tree(self, mocker: MockerFixture) -> None:
        """An HTML template is read and checked while the method loads, and the job names it by its tree as an office one.

        A `files` map ships it as a zip does.
        """
        _stub_the_document_engine(mocker)
        orchestrator = _record_dispatches_to_a_temporal_like_orchestrator(mocker)
        html_mthds = _INVOICE_MTHDS.replace('format        = "docx"', 'format        = "pdf"').replace(_TEMPLATE_PATH, "templates/invoice.html")
        html_template = "<h1>{{ invoice.number }}</h1>"

        response = _build_client().post(
            "/v1/start",
            json={"files": {"invoicing.mthds": html_mthds, "templates/invoice.html": html_template}, "inputs": _INVOICE_INPUTS},
        )

        assert response.status_code == 202, response.text
        (pipe_job,) = orchestrator.pipe_jobs
        tree_files = {"invoicing.mthds": html_mthds.encode("utf-8"), "templates/invoice.html": html_template.encode("utf-8")}
        _assert_the_job_names_the_tree_of(pipe_job=pipe_job, files=tree_files)
        _assert_the_orchestrator_copied_the_tree_of(orchestrator=orchestrator, files=tree_files)
        assert "invoice.number }}" not in pipe_job.model_dump_json()

    def test_a_tree_sent_to_start_is_served_in_this_process_only_until_start_returns(self, mocker: MockerFixture) -> None:
        """Why an orchestrator copies a job's trees before its `start` returns: the runner drops them as soon as it does.

        The runner wrote the sent tree into a temporary directory and its library held it for the request; both are
        gone once `/start` answers, so a job still running in any process reads its files from where its orchestrator
        copied them.
        """
        _stub_the_document_engine(mocker)
        orchestrator = _record_dispatches_to_a_temporal_like_orchestrator(mocker)
        html_mthds = _INVOICE_MTHDS.replace('format        = "docx"', 'format        = "pdf"').replace(_TEMPLATE_PATH, "templates/invoice.html")
        files = {"invoicing.mthds": html_mthds, "templates/invoice.html": "<h1>{{ invoice.number }}</h1>"}

        response = _build_client().post("/v1/start", json={"files": files, "inputs": _INVOICE_INPUTS})

        assert response.status_code == 202, response.text
        (pipe_job,) = orchestrator.pipe_jobs
        crate = pipe_job.library_crate
        assert crate is not None
        assert [copied.tree_digest for copied in orchestrator.copied_trees] == list(crate.tree_digests())
        with pytest.raises(MethodFileUnavailableError):
            asyncio.run(read_stored_trees(tree_digests=crate.tree_digests(), read_scope=pipe_job.job_metadata.run_metadata.read_scope))

    def test_a_file_of_the_method_and_other_bytes_in_resources_under_one_path_are_refused(self, mocker: MockerFixture) -> None:
        """`resources` joins the method's tree, so other bytes under a path the tree holds are two files under one path."""
        _stub_the_document_engine(mocker)
        body: dict[str, Any] = {
            "bundle_b64": _zip_b64({"invoicing.mthds": _INVOICE_MTHDS, _TEMPLATE_PATH: _TEMPLATE_BYTES}),
            "inputs": _INVOICE_INPUTS,
            "resources": {_TEMPLATE_PATH: _b64(b"another template")},
        }

        detail = _assert_problem(_build_client().post("/v1/execute", json=body), status=422, error_type="InvalidResourcePath")

        assert f"'{_TEMPLATE_PATH}'" in detail

    @pytest.mark.parametrize("sends_the_logo", [True, False])
    def test_a_file_only_a_template_s_relative_url_names_travels_in_the_method_s_tree(self, mocker: MockerFixture, sends_the_logo: bool) -> None:
        """No step names the logo, only the template's `<img src>` does: a tree keeps it, and the load's check finds it there.

        Beside inline contents, `resources` still refuses a file no step names, so such a method is sent as a tree.
        """
        _stub_the_document_engine(mocker)
        html_mthds = _INVOICE_MTHDS.replace('format        = "docx"', 'format        = "pdf"').replace(_TEMPLATE_PATH, "templates/invoice.html")
        files: dict[str, Any] = {
            "invoicing.mthds": html_mthds,
            "templates/invoice.html": '<img src="logo.png" alt="Acme"><h1>{{ invoice.number }}</h1>',
        }
        if sends_the_logo:
            files["templates/logo.png"] = {"base64": _b64(b"\x89PNG\r\n\x1a\n a logo")}

        response = _build_client().post("/v1/validate", json={"files": files})

        assert response.status_code == 200, response.text
        verdict = response.json()
        assert verdict["is_valid"] is sends_the_logo, response.text
        if not sends_the_logo:
            assert "logo.png" in json.dumps(verdict["validation_errors"])

    def test_two_bundles_of_a_method_each_read_the_file_beside_them(self, mocker: MockerFixture) -> None:
        """A step names its file from its bundle's own tree path, so two bundles shipping a template each under one relative path both run."""
        _stub_the_document_engine(mocker)
        orchestrator = _record_dispatches_to_a_temporal_like_orchestrator(mocker)
        mthds_b = _INVOICE_MTHDS.replace('domain = "invoicing"', 'domain = "invoicing_b"').replace('main_pipe = "print_invoice"\n', "")
        tree_files = {
            "a/invoicing.mthds": _INVOICE_MTHDS.encode("utf-8"),
            f"a/{_TEMPLATE_PATH}": _TEMPLATE_BYTES,
            "b/invoicing.mthds": mthds_b.encode("utf-8"),
            f"b/{_TEMPLATE_PATH}": b"another template",
        }

        response = _build_client().post("/v1/start", json={"bundle_b64": _zip_b64(tree_files), "inputs": _INVOICE_INPUTS})

        assert response.status_code == 202, response.text
        (pipe_job,) = orchestrator.pipe_jobs
        _assert_the_job_names_the_tree_of(pipe_job=pipe_job, files=tree_files)

    def test_a_method_ref_package_supplies_the_template_its_step_names(
        self, mocker: MockerFixture, install_method_package: Callable[..., Path]
    ) -> None:
        """A fetched package is a method tree read from its commit: its validation reads the template it ships, and a job names that tree."""
        read_templates = _stub_the_document_engine(mocker)
        install_method_package(
            files={"invoicing.mthds": _INVOICE_MTHDS, _TEMPLATE_PATH: _TEMPLATE_BYTES.decode("ascii")}, manifest_toml=_INVOICE_PACKAGE_MANIFEST
        )
        method_ref = f"{STUB_METHOD_ADDRESS}@v0.1.0"
        client = _build_client()

        validated = client.post("/v1/validate", json={"method_ref": method_ref})

        assert validated.status_code == 200, validated.text
        assert validated.json()["is_valid"] is True, validated.text
        assert read_templates
        assert set(read_templates) == {_TEMPLATE_BYTES}

        orchestrator = _record_dispatches_to_a_temporal_like_orchestrator(mocker)
        started = client.post("/v1/start", json={"method_ref": method_ref, "inputs": _INVOICE_INPUTS})

        assert started.status_code == 202, started.text
        (pipe_job,) = orchestrator.pipe_jobs
        tree_files = {
            "METHODS.toml": _INVOICE_PACKAGE_MANIFEST.encode("utf-8"),
            "invoicing.mthds": _INVOICE_MTHDS.encode("utf-8"),
            _TEMPLATE_PATH: _TEMPLATE_BYTES,
        }
        _assert_the_job_names_the_tree_of(pipe_job=pipe_job, files=tree_files)
        _assert_the_orchestrator_copied_the_tree_of(orchestrator=orchestrator, files=tree_files)
        assert started.json()["method_provenance"]["tree_digest"] == digest_of_contents(tree_files)

    def test_a_template_a_method_bundle_ships_is_held_to_the_per_file_limit_of_a_tree(self, mocker: MockerFixture) -> None:
        _stub_the_document_engine(mocker)
        mocker.patch("pipelex_api.method_tree_request.MAX_METHOD_TREE_FILE_BYTES", len(_INVOICE_MTHDS.encode("utf-8")) + 1)

        response = _build_client().post(
            "/v1/execute",
            json={
                "bundle_b64": _zip_b64({"invoicing.mthds": _INVOICE_MTHDS, _TEMPLATE_PATH: bytes(len(_INVOICE_MTHDS) + 2)}),
                "inputs": _INVOICE_INPUTS,
            },
        )

        detail = _assert_problem(response, status=422, error_type="MethodTreeTooLarge")
        assert f"'{_TEMPLATE_PATH}'" in detail
