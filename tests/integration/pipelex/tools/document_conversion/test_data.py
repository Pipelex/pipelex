from typing import ClassVar, NamedTuple


class OfficeFileCase(NamedTuple):
    file_name: str
    format_key: str
    # Measured with Gotenberg 8.40.0 and 9.2.0 on 2026-11-10: printed pages, LibreOffice's default export.
    page_count: int
    # Words the PDF's first page holds, read back with pypdfium2.
    first_page_words: tuple[str, ...]


class DocumentConversionTestData:
    # Where the backends are found: the Gotenberg container's base URL, and the soffice executable (else `soffice` on the PATH).
    GOTENBERG_URL_ENV_VAR = "PIPELEX_TEST_GOTENBERG_URL"
    SOFFICE_BINARY_ENV_VAR = "PIPELEX_TEST_SOFFICE_BINARY"
    DEFAULT_SOFFICE_BINARY = "soffice"

    DOCUMENTS_DIR = "tests/data/documents"

    OFFICE_FILES: ClassVar[list[OfficeFileCase]] = [
        OfficeFileCase(file_name="CV-ELIAS-THORNE.docx", format_key="docx", page_count=2, first_page_words=("ELIAS THORNE", "PROFESSIONAL SUMMARY")),
        OfficeFileCase(file_name="Office-Budget.xlsx", format_key="xlsx", page_count=1, first_page_words=("Item", "Salaries")),
        OfficeFileCase(file_name="Quarterly-Review.pptx", format_key="pptx", page_count=2, first_page_words=("Quarterly Review",)),
    ]
