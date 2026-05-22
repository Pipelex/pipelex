"""Test data for pypdfium2 worker error handling tests."""

from typing import ClassVar

from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind


class Pypdfium2ErrorHandlingTestData:
    """Test cases for pypdfium2 extract worker exception handling.

    Each tuple: (topic, exception_class, exception_message, expected_category, expected_user_action_kind)
    """

    EXTRACTION_ERROR_CASES: ClassVar[list[tuple[str, type[Exception], str, InferenceErrorCategory, UserActionKind]]] = [
        (
            "file_not_found",
            FileNotFoundError,
            "No such file: /tmp/missing.pdf",
            InferenceErrorCategory.CONTENT,
            UserActionKind.CHANGE_INPUT,
        ),
        (
            "invalid_pdf_format",
            ValueError,
            "Not a valid PDF file",
            InferenceErrorCategory.CONTENT,
            UserActionKind.CHANGE_INPUT,
        ),
        (
            "runtime_extraction_failure",
            RuntimeError,
            "Failed to parse PDF structure",
            InferenceErrorCategory.CONTENT,
            UserActionKind.CHANGE_INPUT,
        ),
        (
            "io_error_transient",
            OSError,
            "Permission denied: /tmp/locked.pdf",
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
        ),
    ]
