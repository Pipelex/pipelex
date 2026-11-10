"""Office files at the step: whether a step reads a document as itself or as its PDF, and the PDF it then reads.

A step whose models cannot all read an Office file, or that asks for page views, reads the file's PDF instead, when the
runtime has a document converter (`[runtime.document_conversion]`). One function decides, for every consumer:
`readable_document_for_step` answers the original when the original's format is not one the runtime converts, or when
every model that may serve the step reads it and no page views are asked for; otherwise it answers the PDF. "Every
model that may serve" is the resolved model for a handle or an alias and every member for a waterfall, the rule run
setup's walk uses (`pipelex.cogt.models.model_reference_specs`), so a waterfall whose later member reads only PDFs
never receives a Word file. A PDF helps no model that reads none, so a step whose models read no PDF keeps the original
unless it asks for page views, which are drawn from a PDF whatever the model reads.

**Where it runs.** Where each consumer builds its model input, before the existing checks: in `run_extract` before the
page-view refusal, and after a `PipeLLM`'s or a `PipeJudge`'s prompt has resolved its documents, before the worker
checks the model reads them. Only the URI and the MIME type the model input carries change. The working memory is never
touched: the step's output, the run's inputs and every later step still see the Office file, and the PDF stays a
derived object, never a record.

**What it costs.** Finding or making the PDF reads and writes storage and may call the converter, so it is a leaf of the
content generator (`ContentGeneratorProtocol.make_readable_pdf`): inline in a direct run, dispatched as a leaf operation
by a host runtime, whose step code may run in a workflow that does no I/O. The PDF's bytes never come back here, only
its URI and what the trace says about it.

**What it records.** A `file_converted` trace event per document a step reads as a PDF, on the step's node, written as
soon as the step has its PDF, so a step that then fails still records the conversion it paid for.

**What it leaves alone.** A run with no converter behaves exactly as if conversion did not exist: the original goes to
the model and the existing refusals stand. A dry run converts nothing, and a document of unknown format is left to the
model as before.
"""

from collections.abc import Collection, Sequence
from enum import StrEnum
from typing import NamedTuple

from pipelex import log
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.document.prompt_document import PromptDocument, PromptDocumentBase64, PromptDocumentBinary, PromptDocumentUri
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_reference_specs import resolve_model_specs
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.runtime_hub import get_content_generator, get_optional_document_converter
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.trace_context import TraceContext
from pipelex.tools.document_conversion.document_converter_protocol import is_convertible_format_key
from pipelex.tools.document_conversion.readable_pdf import ReadablePdf
from pipelex.tools.misc.filetype_utils import PDF_FORMAT_KEY, format_key_from_mime_type

PDF_MIME_TYPE = "application/pdf"


class DocumentReading(StrEnum):
    """How a step reads a document: as the file it is given, or as that file's PDF."""

    ORIGINAL = "original"
    PDF = "pdf"

    @property
    def is_pdf(self) -> bool:
        match self:
            case DocumentReading.PDF:
                return True
            case DocumentReading.ORIGINAL:
                return False


def convertible_format_key(*, mime_type: str | None) -> str | None:
    """The format key of a document the runtime converts to PDF, None for any other document and one of unknown format."""
    format_key = format_key_from_mime_type(mime_type=mime_type)
    if format_key is None or not is_convertible_format_key(format_key=format_key):
        return None
    return format_key


def readable_document_for_step(
    *, format_key: str | None, readable_formats_by_model: Sequence[Collection[str]], asks_for_page_views: bool
) -> DocumentReading:
    """Whether a step reads a document as itself or as its PDF.

    Args:
        format_key: The document's format key, as run setup established it; None when unknown.
        readable_formats_by_model: The format keys each model that may serve the step reads, one collection per model;
            empty when the step's model could not be resolved, which leaves the document as it is.
        asks_for_page_views: Whether the step draws the document's pages as images, which only a PDF allows.

    Returns:
        The PDF for a document of a format the runtime converts that some model may not read, or whose pages are drawn;
        the original otherwise.
    """
    if format_key is None or not is_convertible_format_key(format_key=format_key):
        return DocumentReading.ORIGINAL
    if asks_for_page_views:
        return DocumentReading.PDF
    if not readable_formats_by_model:
        return DocumentReading.ORIGINAL
    if all(format_key in readable_formats for readable_formats in readable_formats_by_model):
        return DocumentReading.ORIGINAL
    if not any(PDF_FORMAT_KEY in readable_formats for readable_formats in readable_formats_by_model):
        return DocumentReading.ORIGINAL
    return DocumentReading.PDF


def readable_formats_for_extract(*, model_reference: str) -> list[set[str]]:
    """The formats each extraction model that may serve `model_reference` reads."""
    return [
        model_spec.readable_formats_for_extract
        for model_spec in resolve_model_specs(model_reference=model_reference, model_type=ModelType.TEXT_EXTRACTOR)
    ]


def readable_formats_for_prompt_documents(*, model_reference: str, model_type: ModelType) -> list[set[str]]:
    """The document formats each model of `model_type` that may serve `model_reference` reads, for a prompt's documents."""
    return [model_spec.supported_document_types for model_spec in resolve_model_specs(model_reference=model_reference, model_type=model_type)]


class ReadableExtractInput(NamedTuple):
    """The extraction's input as the step's model reads it, and whether the step reads its document as a PDF.

    `reads_pdf` is True in a dry run too when a live run would convert, which a dry run never does: the step's own
    refusal of page views drawn from a non-PDF then has nothing to refuse.
    """

    extract_input: ExtractInput
    reads_pdf: bool


async def readable_extract_input(
    *,
    extract_input: ExtractInput,
    model_reference: str,
    asks_for_page_views: bool,
    job_metadata: JobMetadata,
    cogt_run_params: CogtRunParams,
) -> ReadableExtractInput:
    """The extraction's input with its document replaced by the document's PDF where the step reads the PDF.

    Raises:
        DocumentConversionError: The conversion refused the document, naming its input.
        DocumentConverterUnavailableError: The converter is busy or unreachable.
    """
    with job_metadata.log_context():
        document_uri = extract_input.document_uri
        format_key = convertible_format_key(mime_type=extract_input.mime_type)
        if document_uri is None or format_key is None or get_optional_document_converter() is None:
            return ReadableExtractInput(extract_input=extract_input, reads_pdf=False)
        reading = readable_document_for_step(
            format_key=format_key,
            readable_formats_by_model=readable_formats_for_extract(model_reference=model_reference),
            asks_for_page_views=asks_for_page_views,
        )
        if not reading.is_pdf:
            return ReadableExtractInput(extract_input=extract_input, reads_pdf=False)
        if cogt_run_params.run_mode.is_dry:
            return ReadableExtractInput(extract_input=extract_input, reads_pdf=True)
        readable_pdf = await read_document_as_pdf(
            source_uri=document_uri,
            format_key=format_key,
            input_name=extract_input.input_name,
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
        )
        return ReadableExtractInput(
            extract_input=extract_input.model_copy(update={"document_uri": readable_pdf.pdf_uri, "mime_type": PDF_MIME_TYPE}),
            reads_pdf=True,
        )


async def readable_prompt_documents(
    *,
    documents: Sequence[PromptDocument],
    model_reference: str,
    model_type: ModelType,
    job_metadata: JobMetadata,
    cogt_run_params: CogtRunParams,
) -> list[PromptDocument]:
    """A prompt's documents, each replaced by its PDF where the step reads the PDF, in the same order.

    A document keeps its place and its token in the prompt: only its URI and MIME type change. A document given as raw
    bytes stays as it is, since no input names it and nothing can key its PDF without reading it again here.

    Raises:
        DocumentConversionError: The conversion refused a document, naming its input.
        DocumentConverterUnavailableError: The converter is busy or unreachable.
    """
    with job_metadata.log_context():
        if not documents or get_optional_document_converter() is None or cogt_run_params.run_mode.is_dry:
            return list(documents)
        readable_formats_by_model = readable_formats_for_prompt_documents(model_reference=model_reference, model_type=model_type)
        readable_documents: list[PromptDocument] = []
        for document in documents:
            source_uri: str
            input_name: str | None
            match document:
                case PromptDocumentUri():
                    source_uri = document.uri
                    input_name = document.input_name
                case PromptDocumentBase64():
                    source_uri = f"data:{document.known_mime_type() or ''};base64,{document.base64_data}"
                    input_name = None
                case PromptDocumentBinary():
                    readable_documents.append(document)
                    continue
            format_key = convertible_format_key(mime_type=document.known_mime_type())
            reading = readable_document_for_step(
                format_key=format_key, readable_formats_by_model=readable_formats_by_model, asks_for_page_views=False
            )
            if format_key is None or not reading.is_pdf:
                readable_documents.append(document)
                continue
            readable_pdf = await read_document_as_pdf(
                source_uri=source_uri,
                format_key=format_key,
                input_name=input_name,
                job_metadata=job_metadata,
                cogt_run_params=cogt_run_params,
            )
            readable_documents.append(PromptDocumentUri(uri=readable_pdf.pdf_uri, mime_type=PDF_MIME_TYPE, input_name=input_name))
        return readable_documents


async def read_document_as_pdf(
    *,
    source_uri: str,
    format_key: str,
    input_name: str | None,
    job_metadata: JobMetadata,
    cogt_run_params: CogtRunParams,
) -> ReadablePdf:
    """The PDF of an Office file, kept or made, recorded on the step's node as a `file_converted` trace event.

    Raises:
        DocumentConversionError: The conversion refused the document, naming its input.
        DocumentConverterUnavailableError: The converter is busy or unreachable.
    """
    with job_metadata.log_context():
        readable_pdf = await get_content_generator().make_readable_pdf(
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            source_uri=source_uri,
            format_key=format_key,
            input_name=input_name,
        )
        _trace_file_conversion(trace_context=job_metadata.trace_context, input_name=input_name, format_key=format_key, readable_pdf=readable_pdf)
        log.info(
            "A step reads an Office file as its PDF",
            fields={
                "pipe_code": job_metadata.pipe_code,
                "input_name": input_name,
                "format_key": format_key,
                "origin": readable_pdf.origin,
                "converter_version": readable_pdf.converter_version,
                "page_count": readable_pdf.page_count,
            },
        )
        return readable_pdf


def _trace_file_conversion(*, trace_context: TraceContext | None, input_name: str | None, format_key: str, readable_pdf: ReadablePdf) -> None:
    """Record the PDF a step reads on the step's own node, when something traces the run.

    The step runs under the trace context its start handed it, whose `parent_node_id` is the step's own node, as every
    record a pipe makes about itself while it runs.
    """
    if trace_context is None or trace_context.parent_node_id is None:
        return
    tracer_manager = GraphTracerManager.get_instance()
    if tracer_manager is None:
        return
    tracer_manager.register_file_conversion(
        lookup_key=trace_context.lookup_key,
        node_id=trace_context.parent_node_id,
        input_name=input_name,
        format_key=format_key,
        readable_pdf=readable_pdf,
    )
