"""Framework-agnostic leaf of an Office file's conversion: the PDF a step reads in place of the file, kept or made.

Single home for "find this file's kept PDF, or convert it and keep the PDF": the direct ``ContentGenerator`` calls it
inline, and a host runtime's content generator dispatches it as a leaf operation, an activity on Temporal, since the
step that needs the PDF may run in workflow code, which does no I/O. The PDF is written to storage here and only its URI
goes back, so its bytes never cross a host runtime's boundary.

**Where the PDF comes from** (`pipelex.tools.document_conversion.readable_pdf` says where it is kept):

1. **A kept PDF.** An object at the PDF's key whose metadata says `export-options: printed-pages` is used as it is,
   whatever its `converter-version`, which the trace records. An object there with no metadata at all, which a storage
   provider keeping none answers, is taken for a printed-pages PDF of unknown version, so a plugin storage still reuses
   its PDFs. An object there that says another export is not this PDF and cannot be replaced, since PDFs are written
   create-only: a source in storage then has its PDF kept under the run's storage scope instead, as a source outside
   storage does.
2. **Otherwise a conversion.** A source in storage is sized first, and one past `max_source_bytes` fails as too large
   without being read; any other source is read, and the converter refuses it past the same size before sending it.
   The PDF's pages are counted with pypdfium2, and the PDF is written create-only with `content_type="application/pdf"`
   and both metadata keys. A concurrent writer winning the race is fine: both wrote a printed-pages PDF of the same
   source, and the step reads the stored one.

Every refusal names the input the document came from. A conversion is never retried here: the backend retries what its
converter's answers say is worth a retry, and a busy converter is `runtime.unavailable`, which the orchestrator may
retry as it retries that code.
"""

import hashlib
import time
from enum import StrEnum
from typing import NamedTuple

from pipelex.cogt.content_generation.assignment_models import DocumentConversionAssignment
from pipelex.cogt.content_generation.read_authorization import authorize_assignment_reads
from pipelex.config import get_config
from pipelex.runtime_hub import get_optional_document_converter, get_storage_provider
from pipelex.tools.document_conversion.document_converter_protocol import (
    EXPORT_OPTIONS_PRINTED_PAGES,
    PDF_METADATA_CONVERTER_VERSION,
    PDF_METADATA_EXPORT_OPTIONS,
    DocumentConverterProtocol,
    is_convertible_format_key,
)
from pipelex.tools.document_conversion.exceptions import (
    ConversionLimitKind,
    DocumentConversionError,
    DocumentConverterAnswerError,
    DocumentConverterMisconfiguredError,
    DocumentFormatNotConvertibleError,
    DocumentTooLargeToConvertError,
    KeptPdfConflictError,
)
from pipelex.tools.document_conversion.readable_pdf import PdfOrigin, ReadablePdf, pdf_key_of, scoped_pdf_key
from pipelex.tools.misc.file_fetch_utils import fetching_for_input
from pipelex.tools.pdf.exceptions import PdfDocumentUnreadableError
from pipelex.tools.storage.exceptions import StorageFileNotFoundError
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME, StorageProviderAbstract
from pipelex.tools.uri.resolved_uri import ResolvedBase64DataUrl, ResolvedHttpUrl, ResolvedLocalPath, ResolvedPipelexStorage
from pipelex.tools.uri.uri_bytes import load_bytes_from_any_uri
from pipelex.tools.uri.uri_resolver import resolve_uri

_PDF_CONTENT_TYPE = "application/pdf"


class _KeptLookup(StrEnum):
    """What the PDF's key holds: nothing, the printed-pages PDF the step reads, or an object that is not that PDF."""

    ABSENT = "absent"
    KEPT = "kept"
    FOREIGN = "foreign"


class _KeptPdfState(NamedTuple):
    lookup: _KeptLookup
    # The kept PDF's `converter-version`, None when it is not kept or its provider keeps no metadata.
    converter_version: str | None = None


async def readable_pdf_of_document(*, conversion_assignment: DocumentConversionAssignment) -> ReadablePdf:
    """The PDF a step reads in place of an Office file: the one kept beside it, or one this call converts and keeps.

    A step never dispatches this in a dry run, which converts nothing, so there is no dry branch: the read scope is still
    authorized first, as every leaf does.

    Raises:
        UriReadRefusedError: The run's read scope does not allow reading the source.
        DocumentConverterMisconfiguredError: This process has no converter, though the step asked for a conversion.
        DocumentFormatNotConvertibleError: The format is not one the runtime converts, which the step checks first.
        DocumentUnreadableByConverterError: The converter could not read the file.
        DocumentTooLargeToConvertError: The file is past `max_source_bytes` or the converter's size, or ran out of time.
        DocumentConverterUnavailableError: The converter is busy or unreachable.
        DocumentConverterAnswerError: The converter answered something that is not a PDF PDFium opens.
        PdfDocumentUnreadableError: A kept PDF could not be opened.
        RemoteFileFetchError: The source could not be fetched.
    """
    authorize_assignment_reads(job_metadata=conversion_assignment.job_metadata, uri_references=conversion_assignment.referenced_uris())
    input_name = conversion_assignment.input_name
    format_key = conversion_assignment.format_key.lower()
    if not is_convertible_format_key(format_key=format_key):
        msg = f"The runtime was asked to convert a file of the format '{format_key}', which it does not convert to PDF."
        raise DocumentFormatNotConvertibleError(msg)
    converter = get_optional_document_converter()
    if converter is None:
        msg = (
            "A step asked for the PDF of an Office file, and this process has no document converter: "
            "set [runtime.document_conversion] backend wherever the steps' leaves run."
        )
        raise DocumentConverterMisconfiguredError(msg)
    storage_provider = get_storage_provider()
    max_source_bytes = get_config().runtime.document_conversion.max_source_bytes
    source_uri = conversion_assignment.source_uri
    storage_scope = conversion_assignment.job_metadata.run_metadata.storage_scope

    source_bytes: bytes
    match resolve_uri(source_uri):
        case ResolvedPipelexStorage() as resolved_storage:
            beside_pdf_key = pdf_key_of(source_key=resolved_storage.storage_uri.removeprefix(PIPELEX_STORAGE_SCHEME))
            beside_state = await _look_up_kept_pdf(storage_provider=storage_provider, pdf_key=beside_pdf_key)
            match beside_state.lookup:
                case _KeptLookup.KEPT:
                    return await _kept_readable_pdf(
                        storage_provider=storage_provider, pdf_key=beside_pdf_key, kept_state=beside_state, input_name=input_name
                    )
                case _KeptLookup.ABSENT:
                    source_bytes = await _load_storage_source(
                        storage_provider=storage_provider,
                        storage_uri=resolved_storage.storage_uri,
                        format_key=format_key,
                        max_source_bytes=max_source_bytes,
                        input_name=input_name,
                    )
                    return await _convert_and_keep(
                        converter=converter,
                        storage_provider=storage_provider,
                        source_bytes=source_bytes,
                        format_key=format_key,
                        pdf_key=beside_pdf_key,
                        input_name=input_name,
                    )
                case _KeptLookup.FOREIGN:
                    # Not this PDF, and PDFs are written create-only: the run keeps its own under its storage scope.
                    source_bytes = await _load_storage_source(
                        storage_provider=storage_provider,
                        storage_uri=resolved_storage.storage_uri,
                        format_key=format_key,
                        max_source_bytes=max_source_bytes,
                        input_name=input_name,
                    )
        case ResolvedHttpUrl() | ResolvedLocalPath() | ResolvedBase64DataUrl():
            with fetching_for_input(input_name=input_name):
                source_bytes = await load_bytes_from_any_uri(source_uri, storage_provider=storage_provider)

    pdf_key = scoped_pdf_key(storage_scope=storage_scope, source_sha256=hashlib.sha256(source_bytes).hexdigest(), format_key=format_key)
    kept_state = await _look_up_kept_pdf(storage_provider=storage_provider, pdf_key=pdf_key)
    match kept_state.lookup:
        case _KeptLookup.KEPT:
            return await _kept_readable_pdf(storage_provider=storage_provider, pdf_key=pdf_key, kept_state=kept_state, input_name=input_name)
        case _KeptLookup.FOREIGN:
            msg = f"The key a run keeps the PDF of input '{input_name}' under holds an object that is not a printed-pages PDF."
            raise KeptPdfConflictError(msg)
        case _KeptLookup.ABSENT:
            return await _convert_and_keep(
                converter=converter,
                storage_provider=storage_provider,
                source_bytes=source_bytes,
                format_key=format_key,
                pdf_key=pdf_key,
                input_name=input_name,
            )


async def _load_storage_source(
    *, storage_provider: StorageProviderAbstract, storage_uri: str, format_key: str, max_source_bytes: int, input_name: str | None
) -> bytes:
    """The bytes of a source in storage, sized first so that one past `max_source_bytes` is refused without being read.

    Raises:
        DocumentTooLargeToConvertError: The source is past `max_source_bytes`.
    """
    source_size = await storage_provider.load_size(storage_uri)
    if source_size > max_source_bytes:
        msg = f"The file is {source_size} bytes, past the {max_source_bytes} bytes a conversion to PDF takes: it was not read."
        too_large = DocumentTooLargeToConvertError(
            msg, format_key=format_key, limit_kind=ConversionLimitKind.BYTES, limit=max_source_bytes, size=source_size
        )
        if input_name is not None:
            too_large.with_input(input_name=input_name)
        raise too_large
    return await storage_provider.load(storage_uri)


async def _look_up_kept_pdf(*, storage_provider: StorageProviderAbstract, pdf_key: str) -> _KeptPdfState:
    """What the PDF's key holds, read from its metadata alone."""
    try:
        metadata = await storage_provider.load_metadata(_storage_uri(key=pdf_key))
    except StorageFileNotFoundError:
        return _KeptPdfState(lookup=_KeptLookup.ABSENT)
    if metadata is None:
        # The provider keeps no metadata: a printed-pages PDF of unknown version, which a plugin storage still reuses.
        return _KeptPdfState(lookup=_KeptLookup.KEPT)
    if metadata.get(PDF_METADATA_EXPORT_OPTIONS) != EXPORT_OPTIONS_PRINTED_PAGES:
        return _KeptPdfState(lookup=_KeptLookup.FOREIGN)
    return _KeptPdfState(lookup=_KeptLookup.KEPT, converter_version=metadata.get(PDF_METADATA_CONVERTER_VERSION))


async def _kept_readable_pdf(
    *, storage_provider: StorageProviderAbstract, pdf_key: str, kept_state: _KeptPdfState, input_name: str | None
) -> ReadablePdf:
    """The kept PDF at `pdf_key`, its pages counted, since what a step reading it is billed on is what the trace explains."""
    pdf_uri = _storage_uri(key=pdf_key)
    pdf_bytes = await storage_provider.load(pdf_uri)
    try:
        page_count = await _count_pages(pdf_bytes=pdf_bytes)
    except PdfDocumentUnreadableError as exc:
        if input_name is not None:
            exc.with_input(input_name=input_name)
        raise
    return ReadablePdf(
        pdf_uri=pdf_uri,
        origin=PdfOrigin.KEPT,
        converter_name=None,
        converter_version=kept_state.converter_version,
        page_count=page_count,
        conversion_seconds=None,
    )


async def _convert_and_keep(
    *,
    converter: DocumentConverterProtocol,
    storage_provider: StorageProviderAbstract,
    source_bytes: bytes,
    format_key: str,
    pdf_key: str,
    input_name: str | None,
) -> ReadablePdf:
    """Convert the source, count the PDF's pages and write it create-only with both metadata keys."""
    started_at = time.monotonic()
    try:
        converted_pdf = await converter.convert_to_pdf(data=source_bytes, format_key=format_key)
    except DocumentConversionError as exc:
        if input_name is not None:
            exc.with_input(input_name=input_name)
        raise
    conversion_seconds = time.monotonic() - started_at
    try:
        page_count = await _count_pages(pdf_bytes=converted_pdf.pdf_bytes)
    except PdfDocumentUnreadableError as exc:
        msg = f"The converter '{converted_pdf.converter_name}' answered a PDF that PDFium could not open."
        raise DocumentConverterAnswerError(msg) from exc
    metadata = {
        PDF_METADATA_CONVERTER_VERSION: converted_pdf.converter_version,
        PDF_METADATA_EXPORT_OPTIONS: EXPORT_OPTIONS_PRINTED_PAGES,
    }
    # A concurrent writer may have kept the same source's PDF since the lookup: the write then stores nothing, and the
    # step reads the stored PDF, a printed-pages export of the same file.
    await storage_provider.store_if_absent(
        data=converted_pdf.pdf_bytes,
        key=pdf_key,
        content_type=_PDF_CONTENT_TYPE,
        checksum_sha256_hex=hashlib.sha256(converted_pdf.pdf_bytes).hexdigest(),
        metadata=metadata,
    )
    return ReadablePdf(
        pdf_uri=_storage_uri(key=pdf_key),
        origin=PdfOrigin.MADE,
        converter_name=converted_pdf.converter_name,
        converter_version=converted_pdf.converter_version,
        page_count=page_count,
        conversion_seconds=conversion_seconds,
    )


async def _count_pages(*, pdf_bytes: bytes) -> int:
    # Deferred import: avoid pulling the pdf rendering SDK at module-load time, as the page-view leaf does.
    from pipelex.tools.pdf.pypdfium2_renderer import pypdfium2_renderer  # ruff: ignore[import-outside-top-level]

    return await pypdfium2_renderer.count_pdf_pages(pdf_input=pdf_bytes)


def _storage_uri(*, key: str) -> str:
    return f"{PIPELEX_STORAGE_SCHEME}{key}"
