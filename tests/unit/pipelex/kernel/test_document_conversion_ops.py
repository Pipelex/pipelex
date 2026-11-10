from collections.abc import Collection, Sequence
from typing import Any

import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.cogt.document.prompt_document import PromptDocument, PromptDocumentBase64, PromptDocumentUri
from pipelex.cogt.document.prompt_document_factory import PromptDocumentFactory
from pipelex.cogt.exceptions import ExtractInputFormatError
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_setting import ExtractSetting
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.errors.problem import ProblemView
from pipelex.kernel.document_conversion_ops import (
    DocumentReading,
    readable_document_for_step,
    readable_extract_input,
    readable_prompt_documents,
)
from pipelex.kernel.extract_ops import build_extract_job_params, run_extract
from pipelex.system.data_inclusion_config import DataInclusionConfig
from pipelex.system.execution_chain import ExecutionAttempt
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.trace_context import TraceContext
from pipelex.tools.document_conversion.exceptions import DocumentUnreadableByConverterError
from pipelex.tools.document_conversion.readable_pdf import PdfOrigin, ReadablePdf
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider

_MODULE = "pipelex.kernel.document_conversion_ops"
_GENERATE_MODULE = "pipelex.cogt.content_generation.document_conversion_generate"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_MIME = "application/pdf"
DOCX_URI = "pipelex-storage://run/assets/report.docx"
PDF_URI = "pipelex-storage://run/assets/report.docx.pdf"
STEP_NODE_ID = "step-node"
READABLE_PDF = ReadablePdf(
    pdf_uri=PDF_URI,
    origin=PdfOrigin.MADE,
    converter_name="gotenberg",
    converter_version="gotenberg-8.40.0",
    page_count=2,
    conversion_seconds=0.5,
)
WORD_AND_PDF = {"docx", "pdf"}
PDF_ONLY = {"pdf"}
IMAGES_ONLY = {"png", "jpg"}
WORD_ONLY = {"docx"}


def _job_metadata(*, traced: bool = False) -> JobMetadata:
    trace_context: TraceContext | None = None
    if traced:
        trace_context = TraceContext(
            graph_id="graph",
            parent_node_id=STEP_NODE_ID,
            node_sequence=0,
            data_inclusion=DataInclusionConfig(pipe_and_concept_registry=False, stuff_json_content=False, error_stack_traces=False),
            run_mode=PipeRunMode.LIVE,
            chain=[ExecutionAttempt(execution="direct", attempt=1)],
        )
    return JobMetadata(
        run_metadata=RunMetadata(storage_scope="run", read_scope=None, user_id="u", pipeline_run_id="run"),
        trace_context=trace_context,
    )


def _wire(*, mocker: MockerFixture, formats_by_model: Sequence[set[str]], has_converter: bool = True) -> Any:
    """A converter configured or not, the models' formats given, and a content generator answering one PDF."""
    mocker.patch(f"{_MODULE}.get_optional_document_converter", return_value=mocker.MagicMock() if has_converter else None)
    model_specs: list[Any] = []
    for formats in formats_by_model:
        model_spec = mocker.MagicMock()
        model_spec.readable_formats_for_extract = formats
        model_spec.supported_document_types = formats
        model_specs.append(model_spec)
    mocker.patch(f"{_MODULE}.resolve_model_specs", return_value=model_specs)
    content_generator = mocker.MagicMock()
    content_generator.make_readable_pdf = mocker.AsyncMock(return_value=READABLE_PDF)
    mocker.patch(f"{_MODULE}.get_content_generator", return_value=content_generator)
    return content_generator.make_readable_pdf


def _run_params(*, run_mode: PipeRunMode = PipeRunMode.LIVE) -> CogtRunParams:
    return CogtRunParams(run_mode=run_mode)


@pytest.mark.asyncio(loop_scope="class")
class TestDocumentConversionOps:
    @pytest.mark.parametrize(
        ("format_key", "formats_by_model", "asks_for_page_views", "expected"),
        [
            pytest.param("docx", [WORD_AND_PDF], False, DocumentReading.ORIGINAL, id="a-model-reading-word-files-gets-the-original"),
            pytest.param("docx", [WORD_AND_PDF], True, DocumentReading.PDF, id="page-views-are-drawn-from-the-pdf"),
            pytest.param("docx", [PDF_ONLY], False, DocumentReading.PDF, id="a-pdf-only-model-gets-the-pdf"),
            pytest.param("docx", [WORD_AND_PDF, PDF_ONLY], False, DocumentReading.PDF, id="a-waterfall-with-a-pdf-only-member-gets-the-pdf"),
            pytest.param("docx", [WORD_AND_PDF, WORD_AND_PDF], False, DocumentReading.ORIGINAL, id="a-waterfall-all-reading-word-files"),
            pytest.param("xlsx", [IMAGES_ONLY], False, DocumentReading.ORIGINAL, id="a-model-reading-no-pdf-keeps-the-original"),
            pytest.param("docx", [], False, DocumentReading.ORIGINAL, id="an-unresolved-model-keeps-the-original"),
            pytest.param("docx", [], True, DocumentReading.PDF, id="an-unresolved-model-still-gets-page-views"),
            pytest.param("docx", [WORD_ONLY], True, DocumentReading.ORIGINAL, id="page-views-for-a-model-reading-no-pdf-keep-the-original"),
            pytest.param("docx", [WORD_ONLY, PDF_ONLY], True, DocumentReading.PDF, id="page-views-for-a-waterfall-with-a-pdf-member"),
            pytest.param("pdf", [IMAGES_ONLY], True, DocumentReading.ORIGINAL, id="a-pdf-is-never-converted"),
            pytest.param(None, [PDF_ONLY], True, DocumentReading.ORIGINAL, id="an-unknown-format-is-left-alone"),
        ],
    )
    async def test_which_document_a_step_reads(
        self,
        format_key: str | None,
        formats_by_model: Sequence[Collection[str]],
        asks_for_page_views: bool,
        expected: DocumentReading,
    ):
        reading = readable_document_for_step(
            format_key=format_key, readable_formats_by_model=formats_by_model, asks_for_page_views=asks_for_page_views
        )

        assert reading == expected

    async def test_an_extraction_reads_the_pdf_and_the_step_records_it(self, mocker: MockerFixture):
        make_readable_pdf = _wire(mocker=mocker, formats_by_model=[PDF_ONLY])
        tracer_manager = mocker.MagicMock()
        mocker.patch(f"{_MODULE}.GraphTracerManager.get_instance", return_value=tracer_manager)
        extract_input = ExtractInput(document_uri=DOCX_URI, mime_type=DOCX_MIME, input_name="report")

        readable_input = await readable_extract_input(
            extract_input=extract_input,
            model_reference="pdf-only-extractor",
            asks_for_page_views=False,
            job_metadata=_job_metadata(traced=True),
            cogt_run_params=_run_params(),
        )

        assert readable_input.reads_pdf
        assert readable_input.extract_input == ExtractInput(document_uri=PDF_URI, mime_type=PDF_MIME, input_name="report")
        assert extract_input.document_uri == DOCX_URI
        assert make_readable_pdf.call_args.kwargs["source_uri"] == DOCX_URI
        assert make_readable_pdf.call_args.kwargs["format_key"] == "docx"
        assert make_readable_pdf.call_args.kwargs["input_name"] == "report"
        tracer_manager.register_file_conversion.assert_called_once_with(
            lookup_key="graph", node_id=STEP_NODE_ID, input_name="report", format_key="docx", readable_pdf=READABLE_PDF
        )

    @pytest.mark.parametrize(
        ("has_converter", "run_mode", "expected_reads_pdf"),
        [
            pytest.param(False, PipeRunMode.LIVE, False, id="no-converter-behaves-as-before"),
            pytest.param(True, PipeRunMode.DRY, True, id="a-dry-run-converts-nothing"),
        ],
    )
    async def test_an_extraction_converts_nothing_without_a_converter_or_in_a_dry_run(
        self, mocker: MockerFixture, has_converter: bool, run_mode: PipeRunMode, expected_reads_pdf: bool
    ):
        make_readable_pdf = _wire(mocker=mocker, formats_by_model=[PDF_ONLY], has_converter=has_converter)
        extract_input = ExtractInput(document_uri=DOCX_URI, mime_type=DOCX_MIME, input_name="report")

        readable_input = await readable_extract_input(
            extract_input=extract_input,
            model_reference="pdf-only-extractor",
            asks_for_page_views=True,
            job_metadata=_job_metadata(),
            cogt_run_params=_run_params(run_mode=run_mode),
        )

        make_readable_pdf.assert_not_called()
        assert readable_input.extract_input == extract_input
        assert readable_input.reads_pdf == expected_reads_pdf

    async def test_page_views_of_a_word_file_are_drawn_from_its_pdf(self, mocker: MockerFixture):
        """With a converter, `run_extract` no longer refuses page views of a Word file: it hands the extraction the PDF."""
        _wire(mocker=mocker, formats_by_model=[WORD_AND_PDF])
        page = PageContent(text_and_images=TextAndImagesContent(text=TextContent(text="page")))
        content_generator = mocker.MagicMock()
        content_generator.make_extract_pages = mocker.AsyncMock(return_value=[page])
        mocker.patch("pipelex.kernel.extract_ops.get_content_generator", return_value=content_generator)
        extract_setting = ExtractSetting(model="word-reading-extractor")

        await run_extract(
            memory=WorkingMemoryFactory.make_empty(),
            extract_input=ExtractInput(document_uri=DOCX_URI, mime_type=DOCX_MIME, input_name="report"),
            extract_setting=extract_setting,
            extract_job_params=build_extract_job_params(extract_setting=extract_setting, should_include_page_views=True),
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.PAGE),
            job_metadata=_job_metadata(),
            cogt_run_params=_run_params(),
            result_name="pages",
        )

        extracted_input = content_generator.make_extract_pages.call_args.kwargs["extract_input"]
        assert extracted_input == ExtractInput(document_uri=PDF_URI, mime_type=PDF_MIME, input_name="report")

    async def test_a_prompt_keeps_its_documents_in_place_and_converts_only_what_a_model_may_not_read(self, mocker: MockerFixture):
        """A waterfall whose second member reads only PDFs: the Word file goes as its PDF, the PDF and an image as they are."""
        make_readable_pdf = _wire(mocker=mocker, formats_by_model=[WORD_AND_PDF | {"png"}, PDF_ONLY | {"png"}])
        pdf_document = PromptDocumentUri(uri="pipelex-storage://run/assets/annex.pdf", mime_type=PDF_MIME, input_name="annex")
        word_document = PromptDocumentUri(uri=DOCX_URI, mime_type=DOCX_MIME, input_name="report")
        documents: list[PromptDocument] = [pdf_document, word_document]

        readable_documents = await readable_prompt_documents(
            documents=documents,
            model_reference="word-then-pdf-waterfall",
            model_type=ModelType.LLM,
            job_metadata=_job_metadata(),
            cogt_run_params=_run_params(),
        )

        assert readable_documents == [pdf_document, PromptDocumentUri(uri=PDF_URI, mime_type=PDF_MIME, input_name="report")]
        assert documents == [pdf_document, word_document]
        make_readable_pdf.assert_called_once()

    @pytest.mark.parametrize(
        ("formats_by_model", "has_converter", "run_mode"),
        [
            pytest.param([WORD_AND_PDF], True, PipeRunMode.LIVE, id="a-model-reading-word-files-gets-the-original"),
            pytest.param([PDF_ONLY], False, PipeRunMode.LIVE, id="no-converter-behaves-as-before"),
            pytest.param([PDF_ONLY], True, PipeRunMode.DRY, id="a-dry-run-converts-nothing"),
            pytest.param([IMAGES_ONLY], True, PipeRunMode.LIVE, id="a-model-reading-no-pdf-keeps-the-original"),
        ],
    )
    async def test_a_prompt_document_left_as_it_is(
        self, mocker: MockerFixture, formats_by_model: Sequence[set[str]], has_converter: bool, run_mode: PipeRunMode
    ):
        make_readable_pdf = _wire(mocker=mocker, formats_by_model=formats_by_model, has_converter=has_converter)
        documents: list[PromptDocument] = [PromptDocumentUri(uri=DOCX_URI, mime_type=DOCX_MIME, input_name="report")]

        readable_documents = await readable_prompt_documents(
            documents=documents,
            model_reference="some-model",
            model_type=ModelType.JUDGMENT,
            job_metadata=_job_metadata(),
            cogt_run_params=_run_params(run_mode=run_mode),
        )

        assert readable_documents == documents
        make_readable_pdf.assert_not_called()

    async def test_a_data_url_input_that_does_not_convert_names_its_input(self, mocker: MockerFixture):
        """An Office data URL left inline, relocation being off, still names its input when the converter refuses it."""
        _wire(mocker=mocker, formats_by_model=[PDF_ONLY])
        mocker.patch(f"{_MODULE}.get_content_generator", return_value=ContentGenerator(generated_content_factory=mocker.MagicMock()))
        mocker.patch(f"{_GENERATE_MODULE}.get_storage_provider", return_value=InMemoryStorageProvider(root={}))
        converter = mocker.MagicMock()
        converter.convert_to_pdf = mocker.AsyncMock(
            side_effect=DocumentUnreadableByConverterError("The converter could not read it.", format_key="xlsx")
        )
        mocker.patch(f"{_GENERATE_MODULE}.get_optional_document_converter", return_value=converter)
        config: Any = mocker.MagicMock()
        config.runtime.document_conversion.max_source_bytes = 50_000_000
        mocker.patch(f"{_GENERATE_MODULE}.get_config", return_value=config)
        mocker.patch.object(PromptDocumentBase64, "known_mime_type", return_value=XLSX_MIME)
        document = PromptDocumentFactory.make_prompt_document(uri=f"data:{XLSX_MIME};base64,UEsDBA==", input_name="budget")

        with pytest.raises(DocumentUnreadableByConverterError) as exc_info:
            await readable_prompt_documents(
                documents=[document],
                model_reference="pdf-only-model",
                model_type=ModelType.LLM,
                job_metadata=_job_metadata(),
                cogt_run_params=_run_params(),
            )

        wire = exc_info.value.to_problem(view=ProblemView.CALLER).to_wire()
        assert wire.get("code") == CoreCode.INPUT_FILE_UNREADABLE
        assert wire.get("params") == {"input": "budget", "file_type": "xlsx", "reason": "conversion_failed"}, wire

    async def test_an_inline_spreadsheet_is_converted_from_its_data_url_and_names_no_input(self, mocker: MockerFixture):
        make_readable_pdf = _wire(mocker=mocker, formats_by_model=[PDF_ONLY])
        mocker.patch.object(PromptDocumentBase64, "known_mime_type", return_value=XLSX_MIME)
        documents: list[PromptDocument] = [PromptDocumentBase64(base64_data="UEsDBA==")]

        readable_documents = await readable_prompt_documents(
            documents=documents,
            model_reference="pdf-only-model",
            model_type=ModelType.LLM,
            job_metadata=_job_metadata(),
            cogt_run_params=_run_params(),
        )

        assert readable_documents == [PromptDocumentUri(uri=PDF_URI, mime_type=PDF_MIME, input_name=None)]
        assert make_readable_pdf.call_args.kwargs["source_uri"] == f"data:{XLSX_MIME};base64,UEsDBA=="
        assert make_readable_pdf.call_args.kwargs["format_key"] == "xlsx"
        assert make_readable_pdf.call_args.kwargs["input_name"] is None

    @pytest.mark.parametrize("has_converter", [True, False])
    async def test_page_views_for_a_model_reading_no_pdf_are_refused_before_any_conversion(self, mocker: MockerFixture, has_converter: bool):
        """A step reached through a condition, which run setup leaves to the step, converts nothing a PDF would not help.

        Its model reads Word files but no PDF, so the page views it asks for cannot be drawn whatever it is given: the step
        refuses them as it did before conversion existed, and its advice does not offer a converter.
        """
        make_readable_pdf = _wire(mocker=mocker, formats_by_model=[WORD_ONLY], has_converter=has_converter)
        content_generator = mocker.MagicMock()
        content_generator.make_extract_pages = mocker.AsyncMock(return_value=[])
        mocker.patch("pipelex.kernel.extract_ops.get_content_generator", return_value=content_generator)
        extract_setting = ExtractSetting(model="word-only-extractor")

        with pytest.raises(ExtractInputFormatError) as exc_info:
            await run_extract(
                memory=WorkingMemoryFactory.make_empty(),
                extract_input=ExtractInput(document_uri=DOCX_URI, mime_type=DOCX_MIME, input_name="report"),
                extract_setting=extract_setting,
                extract_job_params=build_extract_job_params(extract_setting=extract_setting, should_include_page_views=True),
                concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.PAGE),
                job_metadata=_job_metadata(),
                cogt_run_params=_run_params(),
                result_name="pages",
            )

        make_readable_pdf.assert_not_called()
        content_generator.make_extract_pages.assert_not_called()
        assert exc_info.value.message == (
            "Input 'report' is a Word document (.docx), and page views are drawn from a PDF. Give a PDF, or remove page_views from the step."
        )
