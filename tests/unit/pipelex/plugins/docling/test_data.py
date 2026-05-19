"""Test data for Docling worker error handling tests."""

from typing import ClassVar

from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind


class DoclingErrorHandlingTestData:
    """Test cases for Docling extract worker exception handling.

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
            "invalid_format_value_error",
            ValueError,
            "Unsupported document format: .xyz",
            InferenceErrorCategory.CONTENT,
            UserActionKind.CHANGE_INPUT,
        ),
        (
            "runtime_conversion_failure",
            RuntimeError,
            "Docling engine crashed during conversion",
            InferenceErrorCategory.CONTENT,
            UserActionKind.CHANGE_INPUT,
        ),
        (
            "io_error_transient",
            OSError,
            "Disk read error on /tmp/doc.pdf",
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
        ),
    ]
