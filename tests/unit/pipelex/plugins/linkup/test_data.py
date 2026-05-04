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


class LinkupExtractErrorHandlingTestData:
    """Test cases for Linkup extract worker exception handling.

    Each tuple: (topic, exception_class, exception_message, expected_category, expected_message_substring)
    """

    EXTRACT_ERROR_CASES: ClassVar[list[tuple[str, type[Exception], str, InferenceErrorCategory, str]]] = [
        (
            "auth_error",
            LinkupAuthenticationError,
            "Invalid API key",
            InferenceErrorCategory.CONFIGURATION,
            "authentication",
        ),
        (
            "insufficient_credit",
            LinkupInsufficientCreditError,
            "No credits remaining",
            InferenceErrorCategory.CAPACITY,
            "credits exhausted",
        ),
        (
            "rate_limit",
            LinkupTooManyRequestsError,
            "Too many requests",
            InferenceErrorCategory.TRANSIENT,
            "rate limit",
        ),
        (
            "timeout",
            LinkupTimeoutError,
            "Request timed out",
            InferenceErrorCategory.TRANSIENT,
            "timed out",
        ),
        (
            "invalid_request",
            LinkupInvalidRequestError,
            "Bad URL format",
            InferenceErrorCategory.CONTENT,
            "invalid request",
        ),
        (
            "response_too_large",
            LinkupFetchResponseTooLargeError,
            "Response exceeds size limit",
            InferenceErrorCategory.CONTENT,
            "fetch error",
        ),
        (
            "url_is_file",
            LinkupFetchUrlIsFileError,
            "URL points to a file",
            InferenceErrorCategory.CONTENT,
            "fetch error",
        ),
        (
            "failed_fetch",
            LinkupFailedFetchError,
            "Could not fetch URL",
            InferenceErrorCategory.TRANSIENT,
            "linkup error",
        ),
        (
            "no_result",
            LinkupNoResultError,
            "No results found",
            InferenceErrorCategory.TRANSIENT,
            "linkup error",
        ),
        (
            "unknown_error",
            LinkupUnknownError,
            "Something went wrong",
            InferenceErrorCategory.TRANSIENT,
            "linkup error",
        ),
    ]


class LinkupSearchErrorHandlingTestData:
    """Test cases for Linkup search worker exception handling.

    Each tuple: (topic, exception_class, exception_message, expected_category, expected_message_substring)
    """

    SEARCH_ERROR_CASES: ClassVar[list[tuple[str, type[Exception], str, InferenceErrorCategory, str]]] = [
        (
            "auth_error",
            LinkupAuthenticationError,
            "Invalid API key",
            InferenceErrorCategory.CONFIGURATION,
            "authentication",
        ),
        (
            "insufficient_credit",
            LinkupInsufficientCreditError,
            "No credits remaining",
            InferenceErrorCategory.CAPACITY,
            "credits exhausted",
        ),
        (
            "rate_limit",
            LinkupTooManyRequestsError,
            "Too many requests",
            InferenceErrorCategory.TRANSIENT,
            "rate limit",
        ),
        (
            "timeout",
            LinkupTimeoutError,
            "Request timed out",
            InferenceErrorCategory.TRANSIENT,
            "timed out",
        ),
        (
            "invalid_request",
            LinkupInvalidRequestError,
            "Bad query format",
            InferenceErrorCategory.CONTENT,
            "invalid request",
        ),
        (
            "no_result",
            LinkupNoResultError,
            "No results found",
            InferenceErrorCategory.TRANSIENT,
            "linkup error",
        ),
        (
            "unknown_error",
            LinkupUnknownError,
            "Something went wrong",
            InferenceErrorCategory.TRANSIENT,
            "linkup error",
        ),
    ]
