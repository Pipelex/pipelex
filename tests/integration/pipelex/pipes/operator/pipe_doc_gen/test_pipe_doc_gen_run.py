import threading

import pytest
from typing_extensions import override

from pipelex.cogt.doc_gen.doc_gen_format import DocGenSource
from pipelex.cogt.doc_gen.render_job import RenderedDocument, RenderJob, RenderResources
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.runtime_hub import get_storage_provider
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.uri.uri_bytes import load_bytes_from_any_uri
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.doc_gen_helpers import StubEngine, StubEngines
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.test_data import PipeDocGenTestData


class _ThreadRecordingEngine(StubEngine):
    """A stub engine that remembers the name of the thread it printed on."""

    def __init__(self) -> None:
        super().__init__()
        self.thread_names: list[str] = []

    @override
    def render(self, *, job: RenderJob, resources: RenderResources) -> RenderedDocument:
        self.thread_names.append(threading.current_thread().name)
        return super().render(job=job, resources=resources)


class _BrokenEngine(StubEngine):
    """A stub engine that fails the way third-party code can, with an exception nobody declared."""

    @override
    def render(self, *, job: RenderJob, resources: RenderResources) -> RenderedDocument:
        msg = "font cache is corrupt"
        raise RuntimeError(msg)


@pytest.mark.asyncio(loop_scope="class")
class TestPipeDocGenRun:
    async def test_a_run_hands_the_engine_the_layout_and_stores_the_file_under_its_name(self, stub_engines: StubEngines) -> None:
        """The engine gets the layout tree, and the stored file's key ends in the rendered filename."""
        result = await PipelexMTHDSProtocol().execute(
            mthds_contents=[PipeDocGenTestData.bundle(step_fields=PipeDocGenTestData.PDF_LAYOUT_STEP)],
            inputs=PipeDocGenTestData.INVOICE_INPUTS,
        )

        document = result.pipe_output.main_stuff_as(content_type=DocumentContent)
        assert document.filename == "invoice-INV-2026-0142.pdf"
        assert document.url.endswith("/invoice-INV-2026-0142.pdf")
        assert document.mime_type == "application/pdf"
        (job,) = stub_engines.engine.jobs
        assert job.source == DocGenSource.LAYOUT
        assert job.title == "Invoice"
        assert job.layout is not None
        stored = await load_bytes_from_any_uri(document.url, storage_provider=get_storage_provider())
        assert stored.startswith(b"%PDF-stub ")
        assert stub_engines.models == ["reportlab-pdf"]

    async def test_a_step_that_names_its_engine_prints_on_it(self, stub_engines: StubEngines) -> None:
        """`model` chooses the engine: a pdf without a template prints on WeasyPrint when the step names it."""
        await PipelexMTHDSProtocol().execute(
            mthds_contents=[PipeDocGenTestData.bundle(step_fields='format = "pdf"\nmodel = "weasyprint-pdf"')],
            inputs=PipeDocGenTestData.INVOICE_INPUTS,
        )

        assert stub_engines.models == ["weasyprint-pdf"]
        (job,) = stub_engines.engine.jobs
        assert job.source == DocGenSource.LAYOUT

    @pytest.mark.usefixtures("stub_engines")
    async def test_a_sigil_in_the_filename_prints_the_input(self) -> None:
        """`$reference` in the filename prints a Text input's text, as it does in a template."""
        bundle = PipeDocGenTestData.bundle(step_fields='format = "pdf"\nfilename = "invoice-$reference"').replace(
            'inputs      = { invoice = "Invoice" }', 'inputs      = { invoice = "Invoice", reference = "Text" }'
        )
        result = await PipelexMTHDSProtocol().execute(
            mthds_contents=[bundle],
            inputs={**PipeDocGenTestData.INVOICE_INPUTS, "reference": "INV-7"},
        )

        document = result.pipe_output.main_stuff_as(content_type=DocumentContent)
        assert document.filename == "invoice-INV-7.pdf"

    async def test_an_engine_prints_on_the_document_pool_not_the_default_executor(self, stub_engines: StubEngines) -> None:
        """An engine waits on the loop while it reads a file, and reads need the default executor, so engines never hold it."""
        engine = _ThreadRecordingEngine()
        stub_engines.engine = engine
        await PipelexMTHDSProtocol().execute(
            mthds_contents=[PipeDocGenTestData.bundle(step_fields=PipeDocGenTestData.PDF_LAYOUT_STEP)],
            inputs=PipeDocGenTestData.INVOICE_INPUTS,
        )

        (thread_name,) = engine.thread_names
        assert thread_name.startswith("pipelex-doc-gen")

    async def test_an_undeclared_engine_failure_is_a_render_error(self, stub_engines: StubEngines) -> None:
        """Whatever an engine raises beyond a Pipelex error fails the step as a failure to print, naming the file."""
        stub_engines.engine = _BrokenEngine()
        with pytest.raises(PipelineExecutionError) as exc_info:
            await PipelexMTHDSProtocol().execute(
                mthds_contents=[PipeDocGenTestData.bundle(step_fields=PipeDocGenTestData.PDF_LAYOUT_STEP)],
                inputs=PipeDocGenTestData.INVOICE_INPUTS,
            )

        message = str(exc_info.value)
        assert "could not print 'invoice-INV-2026-0142.pdf'" in message
        assert "font cache is corrupt" in message

    async def test_an_html_template_is_rendered_before_the_engine_prints_it(self, stub_engines: StubEngines) -> None:
        """Sigils and the `markdown` filter work in the template, and the engine gets the composed HTML."""
        template = "<h1>$invoice.number</h1><div>{{ invoice.notes | markdown }}</div>"
        await PipelexMTHDSProtocol().execute(
            mthds_contents=[PipeDocGenTestData.bundle(step_fields=f'format = "pdf"\ntemplate = "{template}"')],
            inputs=PipeDocGenTestData.INVOICE_INPUTS,
        )

        assert stub_engines.models == ["weasyprint-pdf"]
        (job,) = stub_engines.engine.jobs
        assert job.source == DocGenSource.HTML
        assert job.html is not None
        assert "INV-2026-0142" in job.html
        assert "<strong>bank transfer</strong>" in job.html
        assert '<a href="https://example.com/terms">' in job.html

    async def test_a_dry_run_outputs_a_mock_document_and_builds_no_engine(self, stub_engines: StubEngines) -> None:
        """The dry run composes for real, then the leaf returns a mock Document without printing."""
        result = await PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY).execute(
            mthds_contents=[PipeDocGenTestData.bundle(step_fields=PipeDocGenTestData.PDF_LAYOUT_STEP)],
            inputs=PipeDocGenTestData.INVOICE_INPUTS,
        )

        document = result.pipe_output.main_stuff_as(content_type=DocumentContent)
        assert document.mime_type == "application/pdf"
        assert document.filename is not None
        assert document.filename.endswith(".pdf")
        assert stub_engines.nb_builds == 0

    @pytest.mark.usefixtures("stub_engines")
    async def test_a_value_absent_from_the_run_s_inputs_fails_the_step(self) -> None:
        """An optional field absent from this run's data fails the strict render, naming the step and the template."""
        with pytest.raises(PipelineExecutionError) as exc_info:
            await PipelexMTHDSProtocol().execute(
                mthds_contents=[PipeDocGenTestData.bundle(step_fields='format = "pdf"\ntemplate = "<p>{{ invoice.notes.upper() }}</p>"')],
                inputs=PipeDocGenTestData.INVOICE_INPUTS_WITHOUT_NOTES,
            )

        message = str(exc_info.value)
        assert "print_invoice" in message
        assert "could not render its template" in message
