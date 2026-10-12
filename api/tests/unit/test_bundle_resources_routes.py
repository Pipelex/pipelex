"""The `resources` a request submits beside its `mthds_contents`: the files its steps read, keyed by the path a step names.

Pins the wire across the routes that load inline contents: the files reach the step that reads them, a file no step
names is refused as the request's fault, a path that cannot name a file inside the bundle is refused, and the count,
per-file and total limits are enforced before anything loads. A live run handed to an orchestrator other than
`direct` carries its office templates by reference to the run's storage, never as bytes in the job.

The hermetic API environment has no document engine, so the step's engine is stubbed and its template check records
the bytes it reads, which is the read the engine's checker would be handed.
"""

import base64
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipelex.cogt.doc_gen.doc_gen_setting import DocGenSetting
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.pipe_operators.doc_gen.pipe_doc_gen import PipeDocGen
from pipelex.pipe_operators.doc_gen.template_file_resource import bundle_resource_of_template_file
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.plugins.orchestrator_registry import OrchestratorRegistry
from pipelex.runtime_bridge.payloads import PipelexPipeDispatchAck, PipelexPipeRunOutput
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pytest_mock import MockerFixture

from pipelex_api.api_config import ApiConfig
from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router
from tests.unit._constants import STUB_METHOD_ADDRESS

_PIPELINE_NS = "pipelex_api.routes.pipelex.pipeline"
_RESOURCES_NS = "pipelex_api.bundle_resources"

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


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


def _stub_the_document_engine(mocker: MockerFixture) -> list[bytes]:
    """Resolve every PipeDocGen step to an engine, and record the template bytes each template check finds for its step.

    The check looks the step's template file up in the library it runs in, where the files sent with the bundle are held.
    """
    read_templates: list[bytes] = []

    async def _record_template_check(pipe: PipeDocGen, *, working_memory: WorkingMemory) -> None:  # noqa: ARG001
        assert pipe.template_file is not None
        resource = bundle_resource_of_template_file(template_file=pipe.template_file)
        assert resource is not None, f"the library holds no file for the template file '{pipe.template_file}'"
        read_templates.append(await resource.read_bytes(storage_provider=InMemoryStorageProvider()))

    mocker.patch.object(PipeDocGen, "resolve_engine", return_value=DocGenSetting(model="stub-docx"))
    mocker.patch.object(PipeDocGen, "check_template_file", autospec=True, side_effect=_record_template_check)
    return read_templates


class _RecordingTemporalStub:
    """An async-capable orchestrator standing in for Temporal: it records the job it is handed and acks it."""

    supports_fire_and_forget = True

    def __init__(self) -> None:
        self.pipe_jobs: list[PipeJob] = []

    async def execute(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeRunOutput:
        msg = "/start drives the fire-and-forget `start` arm; `execute` must not be reached."
        raise NotImplementedError(msg)

    async def start(self, *, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None) -> PipelexPipeDispatchAck:  # noqa: ARG002
        self.pipe_jobs.append(pipe_job)
        return PipelexPipeDispatchAck(pipeline_run_id=pipe_job.job_metadata.run_metadata.pipeline_run_id, workflow_id="wf-1")


def _contents_body(*, route: str, resources: dict[str, str]) -> dict[str, Any]:
    """The route's body carrying the invoice bundle inline with the given resources: the crate routes take `files[]`."""
    match route:
        case "/v1/validate":
            return {"mthds_contents": [_INVOICE_MTHDS], "resources": resources}
        case "/v1/execute":
            return {"mthds_contents": [_INVOICE_MTHDS], "inputs": _INVOICE_INPUTS, "resources": resources}
        case "/v1/codegen":
            return {"files": [{"content": _INVOICE_MTHDS, "source": "invoicing.mthds"}], "kind": "types", "target": "ts-zod", "resources": resources}
        case _:
            return {"files": [{"content": _INVOICE_MTHDS, "source": "invoicing.mthds"}], "resources": resources}


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

    @pytest.mark.parametrize("route", ["/v1/validate", "/v1/execute", "/v1/pipe-io", "/v1/resolve", "/v1/codegen"])
    def test_a_file_no_step_names_is_refused_on_every_route_that_loads_contents(self, mocker: MockerFixture, route: str) -> None:
        _stub_the_document_engine(mocker)
        body = _contents_body(route=route, resources={_TEMPLATE_PATH: _b64(_TEMPLATE_BYTES), "templates/logo.png": _b64(b"png")})

        detail = _assert_problem(_build_client().post(route, json=body), status=422, error_type="BundleResourceNotNamedError")

        assert "'templates/logo.png'" in detail

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

    def test_two_spellings_of_one_file_are_refused(self) -> None:
        response = _build_client().post(
            "/v1/validate",
            json={"mthds_contents": [_INVOICE_MTHDS], "resources": {_TEMPLATE_PATH: _b64(b"a"), f"./{_TEMPLATE_PATH}": _b64(b"b")}},
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

        detail = _assert_problem(_build_client().post(route, json=body), status=422, error_type="ValidationError")

        assert "method_ref" in detail

    @pytest.mark.parametrize("route", ["/v1/validate", "/v1/pipe-io"])
    def test_a_source_label_naming_a_file_on_the_runner_never_reads_beside_it(self, mocker: MockerFixture, tmp_path: Path, route: str) -> None:
        """A caller's absolute source naming a real bundle file, with the template file beside it, reaches nothing on the runner's disk."""
        read_templates = _stub_the_document_engine(mocker)
        bundle_path = tmp_path / "invoicing.mthds"
        bundle_path.write_text(_INVOICE_MTHDS, encoding="utf-8")
        (tmp_path / "templates").mkdir()
        (tmp_path / "templates" / "invoice.docx").write_bytes(_TEMPLATE_BYTES)
        body: dict[str, Any] = (
            {"mthds_contents": [_INVOICE_MTHDS], "mthds_sources": [str(bundle_path)]}
            if route == "/v1/validate"
            else {"files": [{"content": _INVOICE_MTHDS, "source": str(bundle_path)}]}
        )

        response = _build_client().post(route, json=body)

        assert response.status_code == 200, response.text
        verdict = response.json()
        assert verdict["is_valid"] is False
        assert "which was not supplied with its bundle" in str(verdict["validation_errors"])
        assert read_templates == []

    def test_resources_with_no_bundle_to_read_them_are_refused(self) -> None:
        response = _build_client().post("/v1/execute", json={"pipe_code": "print_invoice", "resources": {_TEMPLATE_PATH: _b64(_TEMPLATE_BYTES)}})

        assert "resources accompany the bundle" in _assert_problem(response, status=422, error_type="ValidationError")

    def test_a_run_handed_to_a_remote_orchestrator_carries_its_template_by_reference(self, mocker: MockerFixture) -> None:
        """`/start` on a Temporal-like orchestrator: the job's crate names the stored file, and the run's storage holds its bytes."""
        _stub_the_document_engine(mocker)
        storage_provider = InMemoryStorageProvider()
        mocker.patch(f"{_PIPELINE_NS}.get_storage_provider", return_value=storage_provider)
        mocker.patch(
            f"{_PIPELINE_NS}.get_api_config", return_value=ApiConfig(orchestration_mode="temporal", allow_request_orchestration_mode_override=False)
        )
        orchestrator = _RecordingTemporalStub()
        mocker.patch(f"{_PIPELINE_NS}.get_orchestrator_registry", return_value=OrchestratorRegistry({"temporal": orchestrator}))

        response = _build_client().post(
            "/v1/start",
            json={"mthds_contents": [_INVOICE_MTHDS], "inputs": _INVOICE_INPUTS, "resources": {_TEMPLATE_PATH: _b64(_TEMPLATE_BYTES)}},
        )

        assert response.status_code == 202, response.text
        (pipe_job,) = orchestrator.pipe_jobs
        assert pipe_job.library_crate is not None
        stored = pipe_job.library_crate.bundle_resources[_TEMPLATE_PATH]
        assert stored.content_b64 is None
        assert stored.uri is not None
        assert stored.uri.startswith(f"pipelex-storage://{pipe_job.job_metadata.run_metadata.storage_scope}/assets/bundle/")
        assert storage_provider.root[stored.uri.removeprefix("pipelex-storage://")] == _TEMPLATE_BYTES
        assert _b64(_TEMPLATE_BYTES) not in pipe_job.model_dump_json()
