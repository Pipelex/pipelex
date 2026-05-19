"""Test data for Linkup worker error handling tests."""

from typing import ClassVar

from linkup import (
    LinkupAuthenticationError,
    LinkupFailedFetchError,
    LinkupFetchResponseTooLargeError,
    LinkupFetchUrlIsFileError,
    LinkupInsufficientCreditError,
    LinkupInvalidRequestError,
    LinkupNoResultError,
    LinkupTimeoutError,
    LinkupTooManyRequestsError,
    LinkupUnknownError,
)

from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind


class LinkupExtractErrorHandlingTestData:
    """Test cases for Linkup extract worker exception handling.

    Each tuple: (topic, exception_class, exception_message, expected_category, expected_user_action_kind)
    """

    EXTRACT_ERROR_CASES: ClassVar[list[tuple[str, type[Exception], str, InferenceErrorCategory, UserActionKind]]] = [
        (
            "auth_error",
            LinkupAuthenticationError,
            "Invalid API key",
            InferenceErrorCategory.CONFIGURATION,
            UserActionKind.CHECK_CREDENTIALS,
        ),
        (
            "insufficient_credit",
            LinkupInsufficientCreditError,
            "No credits remaining",
            InferenceErrorCategory.CAPACITY,
            UserActionKind.CHECK_BILLING,
        ),
        (
            "rate_limit",
            LinkupTooManyRequestsError,
            "Too many requests",
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
        ),
        (
            "timeout",
            LinkupTimeoutError,
            "Request timed out",
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
        ),
        (
            "invalid_request",
            LinkupInvalidRequestError,
            "Bad URL format",
            InferenceErrorCategory.CONTENT,
            UserActionKind.CHANGE_INPUT,
        ),
        (
            "response_too_large",
            LinkupFetchResponseTooLargeError,
            "Response exceeds size limit",
            InferenceErrorCategory.CONTENT,
            UserActionKind.CHANGE_INPUT,
        ),
        (
            "url_is_file",
            LinkupFetchUrlIsFileError,
            "URL points to a file",
            InferenceErrorCategory.CONTENT,
            UserActionKind.CHANGE_INPUT,
        ),
        (
            "failed_fetch",
            LinkupFailedFetchError,
            "Could not fetch URL",
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
        ),
        (
            "no_result",
            LinkupNoResultError,
            "No results found",
            InferenceErrorCategory.CONTENT,
            UserActionKind.CHANGE_INPUT,
        ),
        (
            "unknown_error",
            LinkupUnknownError,
            "Something went wrong",
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
        ),
    ]


class LinkupSearchErrorHandlingTestData:
    """Test cases for Linkup search worker exception handling.

    Each tuple: (topic, exception_class, exception_message, expected_category, expected_user_action_kind)
    """

    SEARCH_ERROR_CASES: ClassVar[list[tuple[str, type[Exception], str, InferenceErrorCategory, UserActionKind]]] = [
        (
            "auth_error",
            LinkupAuthenticationError,
            "Invalid API key",
            InferenceErrorCategory.CONFIGURATION,
            UserActionKind.CHECK_CREDENTIALS,
        ),
        (
            "insufficient_credit",
            LinkupInsufficientCreditError,
            "No credits remaining",
            InferenceErrorCategory.CAPACITY,
            UserActionKind.CHECK_BILLING,
        ),
        (
            "rate_limit",
            LinkupTooManyRequestsError,
            "Too many requests",
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
        ),
        (
            "timeout",
            LinkupTimeoutError,
            "Request timed out",
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
        ),
        (
            "invalid_request",
            LinkupInvalidRequestError,
            "Bad query format",
            InferenceErrorCategory.CONTENT,
            UserActionKind.CHANGE_INPUT,
        ),
        (
            "no_result",
            LinkupNoResultError,
            "No results found",
            InferenceErrorCategory.CONTENT,
            UserActionKind.CHANGE_INPUT,
        ),
        (
            "unknown_error",
            LinkupUnknownError,
            "Something went wrong",
            InferenceErrorCategory.TRANSIENT,
            UserActionKind.WAIT_AND_RETRY,
        ),
    ]
