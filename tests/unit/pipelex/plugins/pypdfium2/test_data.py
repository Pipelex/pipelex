"""Test data for pypdfium2 worker error handling tests."""

from typing import ClassVar

from pipelex.cogt.exceptions import InferenceErrorCategory


class Pypdfium2ErrorHandlingTestData:
    """Test cases for pypdfium2 extract worker exception handling.

    Each tuple: (topic, exception_class, exception_message, expected_category, expected_message_substring)
    """

    EXTRACTION_ERROR_CASES: ClassVar[list[tuple[str, type[Exception], str, InferenceErrorCategory, str]]] = [
        (
            "file_not_found",
            FileNotFoundError,
            "No such file: /tmp/missing.pdf",
            InferenceErrorCategory.CONTENT,
            "file not found",
        ),
        (
            "invalid_pdf_format",
            ValueError,
            "Not a valid PDF file",
            InferenceErrorCategory.CONTENT,
            "invalid pdf format",
        ),
        (
            "runtime_extraction_failure",
            RuntimeError,
            "Failed to parse PDF structure",
            InferenceErrorCategory.CONTENT,
            "extraction failed",
        ),
        (
            "io_error_transient",
            OSError,
            "Permission denied: /tmp/locked.pdf",
            InferenceErrorCategory.TRANSIENT,
            "i/o error",
        ),
    ]
