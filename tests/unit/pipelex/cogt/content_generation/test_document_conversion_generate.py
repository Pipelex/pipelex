"""The conversion leaf finds an Office file's kept PDF, or converts the file and keeps the PDF it made.

Storage is the in-memory provider, which keeps metadata, and the converter a stub answering a real PDF, so the page
count is PDFium's. The backends themselves are tested against a real converter in the `document_conversion` suite.
"""

import base64
import hashlib
from pathlib import Path
from typing import Any

import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import DocumentConversionAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.document_conversion_generate import readable_pdf_of_document
from pipelex.errors.problem import ProblemView
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.document_conversion.document_converter_protocol import (
    EXPORT_OPTIONS_PRINTED_PAGES,
    PDF_METADATA_CONVERTER_VERSION,
    PDF_METADATA_EXPORT_OPTIONS,
    ConvertedPdf,
)
from pipelex.tools.document_conversion.exceptions import (
    DocumentConverterMisconfiguredError,
    DocumentTooLargeToConvertError,
    DocumentUnreadableByConverterError,
    KeptPdfConflictError,
)
from pipelex.tools.document_conversion.readable_pdf import PdfOrigin
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider

_MODULE = "pipelex.cogt.content_generation.document_conversion_generate"
PDF_BYTES = Path("tests/data/documents/Job-Offer.pdf").read_bytes()
# A one-page PDF, against the stub converter's two pages, so a result shows which of them it describes.
OTHER_PDF_BYTES = Path("tests/data/documents/solar_system.pdf").read_bytes()
UNOPENABLE_PDF_BYTES = b"%PDF-1.7 truncated"
DOCX_BYTES = Path("tests/data/documents/CV-ELIAS-THORNE.docx").read_bytes()
SOURCE_URI = "pipelex-storage://org/method/run/assets/report.DOCX"
BESIDE_KEY = "org/method/run/assets/report.docx.pdf"
STORAGE_SCOPE = "org/method/run"
CONVERTER_VERSION = "gotenberg-8.40.0"


class _StubConverter:
    """A converter answering the same PDF for any file, or raising what it is told to."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[str] = []
        self._error = error

    @property
    def converter_name(self) -> str:
        return "gotenberg"

    async def get_converter_version(self) -> str:
        return CONVERTER_VERSION

    async def convert_to_pdf(self, *, data: bytes, format_key: str) -> ConvertedPdf:
        self.calls.append(format_key)
        if self._error is not None:
            raise self._error
        assert data
        return ConvertedPdf(pdf_bytes=PDF_BYTES, converter_name=self.converter_name, converter_version=CONVERTER_VERSION)


def _assignment(*, source_uri: str = SOURCE_URI, format_key: str = "docx", input_name: str | None = "report") -> DocumentConversionAssignment:
    return DocumentConversionAssignment(
        job_metadata=JobMetadata(run_metadata=RunMetadata(storage_scope=STORAGE_SCOPE, read_scope=None, user_id="u", pipeline_run_id="run")),
        cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE),
        source_uri=source_uri,
        format_key=format_key,
        input_name=input_name,
    )


def _wire(*, mocker: MockerFixture, converter: _StubConverter | None, max_source_bytes: int = 50_000_000) -> InMemoryStorageProvider:
    storage = InMemoryStorageProvider(root={})
    mocker.patch(f"{_MODULE}.get_storage_provider", return_value=storage)
    mocker.patch(f"{_MODULE}.get_optional_document_converter", return_value=converter)
    config: Any = mocker.MagicMock()
    config.runtime.document_conversion.max_source_bytes = max_source_bytes
    mocker.patch(f"{_MODULE}.get_config", return_value=config)
    return storage


async def _store_source(*, storage: InMemoryStorageProvider) -> None:
    await storage.store(data=DOCX_BYTES, key="org/method/run/assets/report.DOCX")


async def _keep_pdf(*, storage: InMemoryStorageProvider, key: str, data: bytes, converter_version: str, export_options: str) -> None:
    await storage.store_if_absent(
        data=data,
        key=key,
        content_type="application/pdf",
        checksum_sha256_hex=None,
        metadata={PDF_METADATA_CONVERTER_VERSION: converter_version, PDF_METADATA_EXPORT_OPTIONS: export_options},
    )


def _let_a_concurrent_writer_win(*, mocker: MockerFixture, data: bytes, export_options: str) -> None:
    """Have another writer keep `data` at the key between the step's lookup and its own create-only write."""
    real_store_if_absent = InMemoryStorageProvider.store_if_absent

    async def _store_after_the_winner(provider: InMemoryStorageProvider, **kwargs: Any) -> bool:
        await real_store_if_absent(
            provider,
            data=data,
            key=kwargs["key"],
            content_type="application/pdf",
            checksum_sha256_hex=None,
            metadata={PDF_METADATA_CONVERTER_VERSION: "soffice-7.6", PDF_METADATA_EXPORT_OPTIONS: export_options},
        )
        return await real_store_if_absent(provider, **kwargs)

    mocker.patch.object(InMemoryStorageProvider, "store_if_absent", autospec=True, side_effect=_store_after_the_winner)


SCOPED_KEY = f"{STORAGE_SCOPE}/{hashlib.sha256(DOCX_BYTES).hexdigest()}.docx.pdf"


@pytest.mark.asyncio(loop_scope="class")
class TestDocumentConversionGenerate:
    async def test_a_file_in_storage_is_converted_and_its_pdf_kept_beside_it(self, mocker: MockerFixture):
        converter = _StubConverter()
        storage = _wire(mocker=mocker, converter=converter)
        await _store_source(storage=storage)

        readable_pdf = await readable_pdf_of_document(conversion_assignment=_assignment())

        assert readable_pdf.pdf_uri == f"pipelex-storage://{BESIDE_KEY}"
        assert readable_pdf.origin == PdfOrigin.MADE
        assert readable_pdf.converter_name == "gotenberg"
        assert readable_pdf.converter_version == CONVERTER_VERSION
        assert readable_pdf.page_count >= 1
        assert readable_pdf.conversion_seconds is not None
        assert converter.calls == ["docx"]
        assert storage.root[BESIDE_KEY] == PDF_BYTES
        assert await storage.load_metadata(readable_pdf.pdf_uri) == {
            PDF_METADATA_CONVERTER_VERSION: CONVERTER_VERSION,
            PDF_METADATA_EXPORT_OPTIONS: EXPORT_OPTIONS_PRINTED_PAGES,
        }

    async def test_a_kept_pdf_is_reused_whatever_its_version(self, mocker: MockerFixture):
        converter = _StubConverter()
        storage = _wire(mocker=mocker, converter=converter)
        await _store_source(storage=storage)
        await storage.store_if_absent(
            data=PDF_BYTES,
            key=BESIDE_KEY,
            content_type="application/pdf",
            checksum_sha256_hex=None,
            metadata={PDF_METADATA_CONVERTER_VERSION: "soffice-7.6", PDF_METADATA_EXPORT_OPTIONS: EXPORT_OPTIONS_PRINTED_PAGES},
        )

        readable_pdf = await readable_pdf_of_document(conversion_assignment=_assignment())

        assert converter.calls == []
        assert readable_pdf.origin == PdfOrigin.KEPT
        assert readable_pdf.converter_version == "soffice-7.6"
        assert readable_pdf.converter_name is None
        assert readable_pdf.conversion_seconds is None
        assert readable_pdf.page_count >= 1

    async def test_a_pdf_a_provider_keeping_no_metadata_holds_is_reused_as_of_unknown_version(self, mocker: MockerFixture):
        converter = _StubConverter()
        storage = _wire(mocker=mocker, converter=converter)
        await _store_source(storage=storage)
        await storage.store(data=PDF_BYTES, key=BESIDE_KEY)
        mocker.patch.object(InMemoryStorageProvider, "_load_metadata", return_value=None)

        readable_pdf = await readable_pdf_of_document(conversion_assignment=_assignment())

        assert converter.calls == []
        assert readable_pdf.origin == PdfOrigin.KEPT
        assert readable_pdf.converter_version is None

    async def test_an_object_beside_the_file_that_is_not_its_printed_pages_sends_the_pdf_under_the_run(self, mocker: MockerFixture):
        """Written create-only, the foreign object cannot be replaced: the run keeps its own PDF, named by the source's hash."""
        converter = _StubConverter()
        storage = _wire(mocker=mocker, converter=converter)
        await _store_source(storage=storage)
        await storage.store(data=b"%PDF-something else", key=BESIDE_KEY)

        readable_pdf = await readable_pdf_of_document(conversion_assignment=_assignment())

        assert readable_pdf.origin == PdfOrigin.MADE
        assert readable_pdf.pdf_uri == f"pipelex-storage://{STORAGE_SCOPE}/{hashlib.sha256(DOCX_BYTES).hexdigest()}.docx.pdf"
        assert storage.root[BESIDE_KEY] == b"%PDF-something else"

    async def test_a_concurrent_writer_winning_the_key_is_what_the_step_reads_and_the_trace_describes(self, mocker: MockerFixture):
        converter = _StubConverter()
        storage = _wire(mocker=mocker, converter=converter)
        await _store_source(storage=storage)
        _let_a_concurrent_writer_win(mocker=mocker, data=OTHER_PDF_BYTES, export_options=EXPORT_OPTIONS_PRINTED_PAGES)

        readable_pdf = await readable_pdf_of_document(conversion_assignment=_assignment())

        assert converter.calls == ["docx"]
        assert storage.root[BESIDE_KEY] == OTHER_PDF_BYTES
        assert readable_pdf.pdf_uri == f"pipelex-storage://{BESIDE_KEY}"
        assert readable_pdf.origin == PdfOrigin.KEPT
        assert readable_pdf.converter_name is None
        assert readable_pdf.converter_version == "soffice-7.6"
        assert readable_pdf.page_count == 1
        assert readable_pdf.conversion_seconds is None

    async def test_a_concurrent_writer_winning_the_key_with_another_export_is_a_conflict(self, mocker: MockerFixture):
        converter = _StubConverter()
        storage = _wire(mocker=mocker, converter=converter)
        await _store_source(storage=storage)
        _let_a_concurrent_writer_win(mocker=mocker, data=OTHER_PDF_BYTES, export_options="screen")

        with pytest.raises(KeptPdfConflictError):
            await readable_pdf_of_document(conversion_assignment=_assignment())

    async def test_a_kept_pdf_beside_the_file_that_does_not_open_sends_the_pdf_under_the_run(self, mocker: MockerFixture):
        """It cannot be replaced, written create-only: the run converts the file and keeps its PDF under its own scope."""
        converter = _StubConverter()
        storage = _wire(mocker=mocker, converter=converter)
        await _store_source(storage=storage)
        await _keep_pdf(
            storage=storage, key=BESIDE_KEY, data=UNOPENABLE_PDF_BYTES, converter_version="soffice-7.6", export_options=EXPORT_OPTIONS_PRINTED_PAGES
        )

        readable_pdf = await readable_pdf_of_document(conversion_assignment=_assignment())

        assert converter.calls == ["docx"]
        assert readable_pdf.origin == PdfOrigin.MADE
        assert readable_pdf.pdf_uri == f"pipelex-storage://{SCOPED_KEY}"
        assert storage.root[SCOPED_KEY] == PDF_BYTES
        assert storage.root[BESIDE_KEY] == UNOPENABLE_PDF_BYTES

    async def test_a_pdf_kept_under_the_run_that_does_not_open_fails_as_a_conversion_naming_the_input(self, mocker: MockerFixture):
        converter = _StubConverter()
        storage = _wire(mocker=mocker, converter=converter)
        await _keep_pdf(
            storage=storage, key=SCOPED_KEY, data=UNOPENABLE_PDF_BYTES, converter_version="soffice-7.6", export_options=EXPORT_OPTIONS_PRINTED_PAGES
        )
        data_url = f"data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,{base64.b64encode(DOCX_BYTES).decode()}"

        with pytest.raises(DocumentUnreadableByConverterError) as exc_info:
            await readable_pdf_of_document(conversion_assignment=_assignment(source_uri=data_url, input_name="cv"))

        assert converter.calls == []
        wire = exc_info.value.to_problem(view=ProblemView.CALLER).to_wire()
        assert wire.get("code") == CoreCode.INPUT_FILE_UNREADABLE
        assert wire.get("params") == {"input": "cv", "file_type": "docx", "reason": "conversion_failed"}, wire

    async def test_a_file_outside_storage_is_kept_under_the_run_and_reused_by_its_hash(self, mocker: MockerFixture):
        converter = _StubConverter()
        _wire(mocker=mocker, converter=converter)
        data_url = f"data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,{base64.b64encode(DOCX_BYTES).decode()}"

        first = await readable_pdf_of_document(conversion_assignment=_assignment(source_uri=data_url, input_name=None))
        second = await readable_pdf_of_document(conversion_assignment=_assignment(source_uri=data_url, input_name=None))

        assert first.pdf_uri == f"pipelex-storage://{STORAGE_SCOPE}/{hashlib.sha256(DOCX_BYTES).hexdigest()}.docx.pdf"
        assert (first.origin, second.origin) == (PdfOrigin.MADE, PdfOrigin.KEPT)
        assert second.pdf_uri == first.pdf_uri
        assert second.converter_version == CONVERTER_VERSION
        assert converter.calls == ["docx"]

    async def test_a_file_past_the_size_limit_is_refused_without_being_read(self, mocker: MockerFixture):
        converter = _StubConverter()
        storage = _wire(mocker=mocker, converter=converter, max_source_bytes=1000)
        await _store_source(storage=storage)
        load = mocker.spy(InMemoryStorageProvider, "_load_with_metadata")

        with pytest.raises(DocumentTooLargeToConvertError) as exc_info:
            await readable_pdf_of_document(conversion_assignment=_assignment())

        load.assert_not_called()
        assert converter.calls == []
        wire = exc_info.value.to_problem(view=ProblemView.CALLER).to_wire()
        assert wire.get("code") == CoreCode.INPUT_TOO_LARGE
        assert wire.get("params") == {"input": "report", "limit": 1000, "size": len(DOCX_BYTES)}, wire

    async def test_a_conversion_failure_keeps_its_code_and_names_the_input(self, mocker: MockerFixture):
        converter = _StubConverter(error=DocumentUnreadableByConverterError("The converter could not read the file.", format_key="docx"))
        storage = _wire(mocker=mocker, converter=converter)
        await _store_source(storage=storage)

        with pytest.raises(DocumentUnreadableByConverterError) as exc_info:
            await readable_pdf_of_document(conversion_assignment=_assignment(input_name="annexes[2]"))

        wire = exc_info.value.to_problem(view=ProblemView.CALLER).to_wire()
        assert wire.get("code") == CoreCode.INPUT_FILE_UNREADABLE
        assert wire.get("params") == {"input": "annexes[2]", "file_type": "docx", "reason": "conversion_failed"}, wire
        assert BESIDE_KEY not in storage.root

    async def test_a_process_without_a_converter_refuses_as_misconfigured(self, mocker: MockerFixture):
        storage = _wire(mocker=mocker, converter=None)
        await _store_source(storage=storage)

        with pytest.raises(DocumentConverterMisconfiguredError):
            await readable_pdf_of_document(conversion_assignment=_assignment())
