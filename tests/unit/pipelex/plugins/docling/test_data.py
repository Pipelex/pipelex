"""Test data for Docling worker error handling tests."""

from typing import ClassVar

from pipelex.cogt.exceptions import InferenceErrorCategory


class DoclingErrorHandlingTestData:
    """Test cases for Docling extract worker exception handling.

    Each tuple: (topic, exception_class, exception_message, expected_category, expected_message_substring)
    """

    EXTRACTION_ERROR_CASES: ClassVar[list[tuple[str, type[Exception], str, InferenceErrorCategory, str]]] = [
        (
            "file_not_found",
            FileNotFoundError,
            "No such file: /tmp/missing.pdf",
            InferenceErrorCategory.CONFIGURATION,
            "file not found",
        ),
        (
            "invalid_format_value_error",
            ValueError,
            "Unsupported document format: .xyz",
            InferenceErrorCategory.CONTENT,
            "invalid document format",
        ),
        (
            "runtime_conversion_failure",
            RuntimeError,
            "Docling engine crashed during conversion",
            InferenceErrorCategory.CONTENT,
            "conversion failed",
        ),
        (
            "io_error_transient",
            OSError,
            "Disk read error on /tmp/doc.pdf",
            InferenceErrorCategory.TRANSIENT,
            "i/o error",
        ),
    ]
