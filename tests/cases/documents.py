"""Document constants for testing."""

from typing import ClassVar

from pipelex.urls import URLs


class DocumentTestCases:
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
    PPTX_FILE_PATH_1 = f"{TEST_DOCUMENT_DIRECTORY}/Quarterly-Review.pptx"
    XLSX_FILE_PATH_1 = f"{TEST_DOCUMENT_DIRECTORY}/Office-Budget.xlsx"
    HTML_FILE_PATH_1 = f"{TEST_DOCUMENT_DIRECTORY}/Solar-Article.html"

    DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    PPTX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    XLSX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    HTML_MIME_TYPE = "text/html"

    # Documents in a format other than PDF, each with the MIME type run setup would stamp on it and a
    # phrase its extraction must contain. An extract model reads one only if it declares its format,
    # and is refused with ExtractInputFormatError otherwise.
    NON_PDF_DOCUMENT_CASES: ClassVar[list[tuple[str, str, str]]] = [  # file_path, mime_type, expected_phrase
        (DOCX_FILE_PATH_1, DOCX_MIME_TYPE, "ELIAS THORNE"),
        (PPTX_FILE_PATH_1, PPTX_MIME_TYPE, "Revenue grew twelve percent"),
        (XLSX_FILE_PATH_1, XLSX_MIME_TYPE, "Salaries"),
        (HTML_FILE_PATH_1, HTML_MIME_TYPE, "eight planets"),
    ]

    # Remote URLs
    PDF_FILE_URL_1 = URLs.pdf_example_1
    PDF_FILE_URL_2 = URLs.pdf_example_2

    DOCUMENT_URLS: ClassVar[list[str]] = [
        PDF_FILE_URL_1,
        PDF_FILE_URL_2,
    ]

    # Web URLs
    WEB_URL_1 = "https://books.toscrape.com/catalogue/cravings-recipes-for-what-you-want-to-eat_589/index.html"
    WEB_URL_2 = "https://www.scrapethissite.com/pages/"
    WEB_URL_3 = "https://www.allrecipes.com/recipe/91192/french-onion-soup-gratinee/"

    WEB_URLS: ClassVar[list[str]] = [
        # WEB_URL_1,
        # WEB_URL_2,
        WEB_URL_3,
    ]
