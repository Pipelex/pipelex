"""A bundle loaded from content strings brings the template files its PipeDocGen steps read, as the runner's routes receive it."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from typing_extensions import override

from pipelex.cogt.doc_gen.doc_gen_format import DocGenSource
from pipelex.cogt.doc_gen.template_check import TemplateFinding, TemplateFindingSeverity
from pipelex.core.bundle_resources.bundle_resource import BundleResources, make_bundle_resources
from pipelex.core.bundle_resources.exceptions import BundleResourceNotNamedError
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.interpreter_hub import get_current_library, get_library_manager, get_pipe_run, set_current_library
from pipelex.libraries.bundle_resources import relocate_run_resources
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_protocol import PipeRunProtocol
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.runtime_hub import get_storage_provider
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.doc_gen_helpers import StubEngines, write_bundle
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.test_data import PipeDocGenTestData

if TYPE_CHECKING:
    from pipelex.libraries.library_crate import LibraryCrate

_DOCX_TEMPLATE_STEP = 'format = "docx"\ntemplate_file = "templates/invoice.docx"'
_DOCX_BYTES = b"PK docx template bytes"


def _docx_resources() -> BundleResources:
    return make_bundle_resources(files={"./templates/invoice.docx": _DOCX_BYTES})


class _WorkerLikePipeRun(PipeRunProtocol):
    """Runs a job the way a remote worker does: its crate's office templates relocated to storage, loaded into a library of its own.

    The worker rebuilds the pipe from the crate and runs its own copy, which finds only a reference to its template in
    the library it runs in, so its print stage reads the bytes back from the run's storage, as a Temporal activity does.
    """

    def __init__(self) -> None:
        self.relocated_crate: LibraryCrate | None = None

    @override
    async def run(self, pipe_job: PipeJob, *, delivery_assignment: DeliveryAssignment | None = None) -> PipeOutput:
        assert pipe_job.library_crate is not None
        relocated_crate = await relocate_run_resources(
            crate=pipe_job.library_crate,
            storage_provider=get_storage_provider(),
            storage_scope=pipe_job.job_metadata.run_metadata.storage_scope,
        )
        self.relocated_crate = relocated_crate
        library_manager = get_library_manager()
        submitter_library_id = get_current_library()
        worker_library_id = f"worker-{pipe_job.job_metadata.run_metadata.pipeline_run_id}"
        worker_library = library_manager.open_fresh_library(library_id=worker_library_id)
        submitter_class_registry = library_manager.get_library(library_id=submitter_library_id).get_class_registry()
        if submitter_class_registry is not None:
            worker_library.set_class_registry(submitter_class_registry)
        set_current_library(library_id=worker_library_id)
        try:
            library_manager.load_from_crate(library_id=worker_library_id, crate=relocated_crate, is_crate_prevalidated=True)
            worker_pipe = library_manager.get_library(library_id=worker_library_id).pipe_library.get_required_pipe(pipe_code=pipe_job.pipe.pipe_ref)
            worker_job = pipe_job.model_copy(update={"pipe": worker_pipe, "library_crate": relocated_crate})
            return await get_pipe_run().run(worker_job, delivery_assignment=delivery_assignment)
        finally:
            set_current_library(library_id=submitter_library_id)
            library_manager.teardown(library_id=worker_library_id)


@pytest.mark.asyncio(loop_scope="class")
class TestPipeDocGenBundleResources:
    async def test_a_bundle_validates_with_its_template_file_and_the_check_runs_on_its_bytes(self, stub_engines: StubEngines) -> None:
        """The dry run hands the engine's checker the bytes submitted with the bundle, found by the path the step names."""
        await validate_bundle(
            mthds_contents=[PipeDocGenTestData.bundle(step_fields=_DOCX_TEMPLATE_STEP)],
            bundle_resources=_docx_resources(),
        )

        (request,) = stub_engines.check_requests
        assert request.template == _DOCX_BYTES
        assert request.template_name == "templates/invoice.docx"

    async def test_the_check_s_errors_on_a_submitted_template_fail_the_validation(self, stub_engines: StubEngines) -> None:
        stub_engines.findings = [TemplateFinding(severity=TemplateFindingSeverity.ERROR, message="The tag {{ invoice.totl }} names no field")]

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(
                mthds_contents=[PipeDocGenTestData.bundle(step_fields=_DOCX_TEMPLATE_STEP)],
                bundle_resources=_docx_resources(),
            )

        assert "invoice.totl" in str(exc_info.value.to_error_report().model_dump())

    @pytest.mark.usefixtures("stub_engines")
    async def test_a_template_file_not_supplied_is_refused_saying_so(self) -> None:
        """The refusal is the bundle's verdict, located on the step, and names the path the file is expected under."""
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[PipeDocGenTestData.bundle(step_fields=_DOCX_TEMPLATE_STEP)])

        report = str(exc_info.value.to_error_report().model_dump())
        assert "names the template file 'templates/invoice.docx', which was not supplied with its bundle" in report

    @pytest.mark.usefixtures("stub_engines")
    async def test_a_file_no_step_names_is_refused_as_the_request_s_fault_not_as_a_verdict(self) -> None:
        resources = make_bundle_resources(files={"templates/invoice.docx": _DOCX_BYTES, "templates/logo.png": b"png"})

        with pytest.raises(BundleResourceNotNamedError) as exc_info:
            await validate_bundle(mthds_contents=[PipeDocGenTestData.bundle(step_fields=_DOCX_TEMPLATE_STEP)], bundle_resources=resources)

        assert "'templates/logo.png'" in exc_info.value.message

    @pytest.mark.usefixtures("stub_engines")
    async def test_a_submitted_html_template_is_read_and_checked_when_the_method_loads(self) -> None:
        """An HTML template file is checked against the inputs at load, as one beside a bundle on disk is."""
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(
                mthds_contents=[PipeDocGenTestData.bundle(step_fields='format = "pdf"\ntemplate_file = "invoice.html"')],
                bundle_resources=make_bundle_resources(files={"invoice.html": b"<h1>{{ invoice.numbr }}</h1>"}),
            )

        assert "numbr" in str(exc_info.value.to_error_report().model_dump())

    async def test_a_run_prints_with_the_submitted_html_template(self, stub_engines: StubEngines) -> None:
        await PipelexMTHDSProtocol(bundle_resources=make_bundle_resources(files={"invoice.html": b"<h1>{{ invoice.number }}</h1>"})).execute(
            mthds_contents=[PipeDocGenTestData.bundle(step_fields='format = "pdf"\ntemplate_file = "invoice.html"')],
            inputs=PipeDocGenTestData.INVOICE_INPUTS,
        )

        (job,) = stub_engines.engine.jobs
        assert job.source == DocGenSource.HTML
        assert job.html == "<h1>INV-2026-0142</h1>"

    async def test_a_run_hands_the_engine_the_submitted_template_file(self, stub_engines: StubEngines) -> None:
        result = await PipelexMTHDSProtocol(bundle_resources=_docx_resources()).execute(
            mthds_contents=[PipeDocGenTestData.bundle(step_fields=_DOCX_TEMPLATE_STEP)],
            inputs=PipeDocGenTestData.INVOICE_INPUTS,
        )

        document = result.pipe_output.main_stuff_as(content_type=DocumentContent)
        assert document.filename is not None
        assert document.filename.endswith(".docx")
        (job,) = stub_engines.engine.jobs
        assert job.source == DocGenSource.TEMPLATE_FILE
        assert job.template == _DOCX_BYTES
        assert job.template_name == "templates/invoice.docx"
        assert job.data["invoice"]["number"] == "INV-2026-0142"

    async def test_a_dry_run_checks_the_submitted_template_file_and_prints_nothing(self, stub_engines: StubEngines) -> None:
        result = await PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, bundle_resources=_docx_resources()).execute(
            mthds_contents=[PipeDocGenTestData.bundle(step_fields=_DOCX_TEMPLATE_STEP)],
            inputs=PipeDocGenTestData.INVOICE_INPUTS,
        )

        document = result.pipe_output.main_stuff_as(content_type=DocumentContent)
        assert document.filename is not None
        assert document.filename.endswith(".docx")
        (request,) = stub_engines.check_requests
        assert request.template == _DOCX_BYTES
        assert stub_engines.engine.jobs == []

    async def test_a_run_handed_to_a_remote_worker_prints_from_the_run_s_storage(self, stub_engines: StubEngines) -> None:
        """The relocated crate carries a reference, the worker's library holds only that, and the print stage reads the stored bytes."""
        worker_like_pipe_run = _WorkerLikePipeRun()

        await PipelexMTHDSProtocol(bundle_resources=_docx_resources(), pipe_run=worker_like_pipe_run).execute(
            mthds_contents=[PipeDocGenTestData.bundle(step_fields=_DOCX_TEMPLATE_STEP)],
            inputs=PipeDocGenTestData.INVOICE_INPUTS,
        )

        assert worker_like_pipe_run.relocated_crate is not None
        stored = worker_like_pipe_run.relocated_crate.bundle_resources["templates/invoice.docx"]
        assert stored.uri is not None
        assert stored.content_b64 is None
        (job,) = stub_engines.engine.jobs
        assert job.template == _DOCX_BYTES

    @pytest.mark.parametrize(
        ("step_fields", "template_name", "template_bytes"),
        [
            pytest.param(_DOCX_TEMPLATE_STEP, "templates/invoice.docx", _DOCX_BYTES, id="office"),
            pytest.param('format = "pdf"\ntemplate_file = "invoice.html"', "invoice.html", b"<h1>{{ invoice.number }}</h1>", id="html"),
        ],
    )
    async def test_a_caller_s_source_label_never_reads_beside_it_on_this_host(
        self, stub_engines: StubEngines, tmp_path: Path, step_fields: str, template_name: str, template_bytes: bytes
    ) -> None:
        """A label naming a real bundle file on this host, beside which the template file exists, still reads nothing from disk."""
        bundle_path = write_bundle(directory=tmp_path, step_fields=step_fields)
        (tmp_path / template_name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / template_name).write_bytes(template_bytes)

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[bundle_path.read_text(encoding="utf-8")], mthds_sources=[str(bundle_path)])

        assert "which was not supplied with its bundle" in str(exc_info.value.to_error_report().model_dump())
        assert stub_engines.check_requests == []

    async def test_a_source_the_bundle_s_text_writes_on_its_step_never_reads_beside_it_on_this_host(
        self, stub_engines: StubEngines, tmp_path: Path
    ) -> None:
        """The step's own `source` key is overwritten when the pipe is built, on the validation path and on the run path."""
        bundle_path = write_bundle(directory=tmp_path, step_fields=_DOCX_TEMPLATE_STEP)
        (tmp_path / "templates").mkdir()
        (tmp_path / "templates" / "invoice.docx").write_bytes(_DOCX_BYTES)
        content = PipeDocGenTestData.bundle(step_fields=f'{_DOCX_TEMPLATE_STEP}\nsource = "{bundle_path}"')

        with pytest.raises(ValidateBundleError) as validate_exc_info:
            await validate_bundle(mthds_contents=[content])
        with pytest.raises(ValidateBundleError) as run_exc_info:
            await PipelexMTHDSProtocol().execute(mthds_contents=[content], inputs=PipeDocGenTestData.INVOICE_INPUTS)

        for exc_info in (validate_exc_info, run_exc_info):
            assert "which was not supplied with its bundle" in str(exc_info.value.to_error_report().model_dump())
        assert stub_engines.check_requests == []
        assert stub_engines.engine.jobs == []

    async def test_a_step_read_from_a_file_here_reads_beside_it_and_never_a_submitted_file(self, stub_engines: StubEngines, tmp_path: Path) -> None:
        """A host library's step and a submitted step naming the same template path each read their own file, here and on a worker.

        A worker's library holds the crate's submitted files before it builds any pipe, the host library's included,
        so the host step must not take the submitted file for its own there either.
        """
        host_dir = tmp_path / "host"
        host_dir.mkdir()
        step_fields = 'format = "docx"\ntemplate_file = "invoice.docx"'
        (host_dir / "invoice.mthds").write_text(
            PipeDocGenTestData.bundle(step_fields=step_fields).replace("doc_gen_tests", "doc_gen_host"), encoding="utf-8"
        )
        (host_dir / "invoice.docx").write_bytes(b"host template")
        submitted = make_bundle_resources(files={"invoice.docx": b"submitted template"})
        host_inputs: dict[str, Any] = {"invoice": {**PipeDocGenTestData.INVOICE_INPUTS["invoice"], "concept": "doc_gen_host.Invoice"}}
        runs: list[tuple[str, dict[str, Any]]] = [
            ("doc_gen_host.print_invoice", host_inputs),
            ("doc_gen_tests.print_invoice", PipeDocGenTestData.INVOICE_INPUTS),
        ]

        for pipe_run in (None, _WorkerLikePipeRun()):
            for pipe_code, inputs in runs:
                await PipelexMTHDSProtocol(library_dirs=[str(host_dir)], bundle_resources=submitted, pipe_run=pipe_run).execute(
                    pipe_code=pipe_code,
                    mthds_contents=[PipeDocGenTestData.bundle(step_fields=step_fields)],
                    inputs=inputs,
                )

        assert [job.template for job in stub_engines.engine.jobs] == [b"host template", b"submitted template"] * 2
