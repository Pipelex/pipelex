from pathlib import Path

import pypdfium2 as pdfium
import pytest

from pipelex.tools.document_conversion.document_converter_protocol import PDF_MAGIC, DocumentConverterProtocol
from pipelex.tools.document_conversion.exceptions import DocumentUnreadableByConverterError
from tests.integration.pipelex.tools.document_conversion.test_data import DocumentConversionTestData, OfficeFileCase


def _read_pdf(*, pdf_bytes: bytes) -> tuple[int, str]:
    """The PDF's page count and the text of its first page."""
    document = pdfium.PdfDocument(pdf_bytes)
    try:
        page_count = len(document)
        text_page = document[0].get_textpage()
        first_page_text: str = text_page.get_text_bounded()  # pyright: ignore[reportUnknownMemberType]
    finally:
        document.close()
    return page_count, first_page_text


@pytest.mark.document_conversion
@pytest.mark.asyncio(loop_scope="class")
class TestDocumentConversionBackends:
    @pytest.mark.parametrize("office_file", DocumentConversionTestData.OFFICE_FILES, ids=lambda case: case.file_name)
    async def test_an_office_file_converts_to_its_printed_pages(
        self, document_converter: DocumentConverterProtocol, office_file: OfficeFileCase
    ) -> None:
        source_bytes = (Path(DocumentConversionTestData.DOCUMENTS_DIR) / office_file.file_name).read_bytes()

        converted = await document_converter.convert_to_pdf(data=source_bytes, format_key=office_file.format_key)

        assert converted.pdf_bytes.startswith(PDF_MAGIC)
        assert converted.converter_name == document_converter.converter_name
        assert converted.converter_version == await document_converter.get_converter_version()
        assert converted.converter_version
        page_count, first_page_text = _read_pdf(pdf_bytes=converted.pdf_bytes)
        assert page_count == office_file.page_count
        for word in office_file.first_page_words:
            assert word in first_page_text

    async def test_a_truncated_file_is_unreadable(self, document_converter: DocumentConverterProtocol) -> None:
        """Gotenberg answers a truncated Word file `500` (8.40) or `400` (9.2), and soffice writes no PDF of it."""
        source_bytes = (Path(DocumentConversionTestData.DOCUMENTS_DIR) / "CV-ELIAS-THORNE.docx").read_bytes()

        with pytest.raises(DocumentUnreadableByConverterError):
            await document_converter.convert_to_pdf(data=source_bytes[:3000], format_key="docx")
