"""Document constants for testing."""

from typing import ClassVar


class PDFTestCases:
    """PDF document test constants."""

    # Directory paths
    TEST_DOCUMENT_DIRECTORY = "tests/data/documents"

    # Local file paths
    PDF_FILE_PATH_1 = f"{TEST_DOCUMENT_DIRECTORY}/solar_system.pdf"
    PDF_FILE_PATH_2 = f"{TEST_DOCUMENT_DIRECTORY}/illustrated_train_article.pdf"
    DOCUMENT_FILE_PATHS: ClassVar[list[str]] = [
        PDF_FILE_PATH_1,
        PDF_FILE_PATH_2,
    ]

    # Remote URLs
    DOCUMENT_URLS: ClassVar[list[str]] = ["https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"]
