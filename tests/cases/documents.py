"""Document constants for testing."""

from typing import ClassVar


class PDFTestCases:
    """PDF document test constants."""

    # Directory paths
    TEST_DOCUMENT_DIRECTORY = "tests/data/documents"

    # Local file paths
    PDF_FILE_PATH_1 = f"{TEST_DOCUMENT_DIRECTORY}/Job-Offer-Scan.pdf"
    PDF_FILE_PATH_2 = f"{TEST_DOCUMENT_DIRECTORY}/Job-Offer.pdf"
    PDF_FILE_PATH_3 = f"{TEST_DOCUMENT_DIRECTORY}/solar_system.pdf"
    PDF_FILE_PATH_4 = f"{TEST_DOCUMENT_DIRECTORY}/illustrated_train_article.pdf"
    PDF_FILE_PATH_CV = f"{TEST_DOCUMENT_DIRECTORY}/John-Doe-CV.pdf"
    PDF_FILE_PATHS: ClassVar[list[str]] = [
        PDF_FILE_PATH_1,
        PDF_FILE_PATH_2,
        PDF_FILE_PATH_3,
        PDF_FILE_PATH_4,
    ]
    DOCX_FILE_PATH_1 = f"{TEST_DOCUMENT_DIRECTORY}/CV-ELIAS-THORNE.docx"
    DOCUMENT_FILE_PATHS: ClassVar[list[str]] = [
        # PDF_FILE_PATH_1,
        # PDF_FILE_PATH_2,
        # PDF_FILE_PATH_3,
        # PDF_FILE_PATH_4,
        DOCX_FILE_PATH_1,
    ]

    # Remote URLs
    PDF_FILE_URL_1 = "https://pipelex-web.s3.amazonaws.com/demo/Job-Offer.pdf"
    PDF_FILE_URL_2 = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
    DOCUMENT_URLS: ClassVar[list[str]] = [
        PDF_FILE_URL_1,
        PDF_FILE_URL_2,
    ]
