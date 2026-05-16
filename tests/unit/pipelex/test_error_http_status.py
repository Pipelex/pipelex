"""Unit tests for the error_domain -> HTTP-status mapping."""

from __future__ import annotations

import pytest

from pipelex.base_exceptions import ErrorDomain, ErrorReport, error_domain_to_http_status
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata


class TestErrorHttpStatus:
    @pytest.mark.parametrize(
        ("error_domain", "expected_status"),
        [
            (ErrorDomain.INPUT, 422),
            (ErrorDomain.CONFIG, 500),
            (ErrorDomain.RUNTIME, 500),
            (None, 500),
            ("input", 422),
            ("config", 500),
            ("runtime", 500),
            ("domain-from-the-future", 500),
        ],
    )
    def test_error_domain_to_http_status(self, error_domain: ErrorDomain | str | None, expected_status: int) -> None:
        """The mapping yields 422 for INPUT and 500 for CONFIG/RUNTIME/unknown/None, for enum or raw-string input."""
        assert error_domain_to_http_status(error_domain) == expected_status

    @pytest.mark.parametrize(
        ("error_domain", "expected_status"),
        [
            ("input", 422),
            ("config", 500),
            ("runtime", 500),
            (None, 500),
        ],
    )
    def test_error_report_http_status_follows_domain(self, error_domain: str | None, expected_status: int) -> None:
        """ErrorReport.http_status follows error_domain when there is no provider 429."""
        report = ErrorReport(error_type="SomeError", message="boom", error_domain=error_domain)
        assert report.http_status == expected_status

    def test_provider_429_takes_precedence_over_domain(self) -> None:
        """A provider 429 overrides the domain default and exposes retry_after_seconds."""
        provider_metadata = ProviderErrorMetadata(
            provider="openai",
            sdk_exception_type="RateLimitError",
            status_code=429,
            retry_after_seconds=12.0,
        )
        report = ErrorReport(
            error_type="LLMCompletionError",
            message="rate limited",
            error_domain="input",
            provider_metadata=provider_metadata,
        )
        assert report.http_status == 429
        assert report.provider_metadata is not None
        assert report.provider_metadata.retry_after_seconds == 12.0

    def test_non_429_provider_status_does_not_override_domain(self) -> None:
        """A non-429 provider status code leaves the domain default in place."""
        provider_metadata = ProviderErrorMetadata(
            provider="openai",
            sdk_exception_type="BadRequestError",
            status_code=400,
        )
        report = ErrorReport(
            error_type="LLMCompletionError",
            message="bad request",
            error_domain="input",
            provider_metadata=provider_metadata,
        )
        assert report.http_status == 422

    def test_unknown_error_domain_falls_back_to_500(self) -> None:
        """An unrecognized error_domain string (e.g. from a newer Pipelex) yields 500, not a crash."""
        report = ErrorReport(error_type="SomeError", message="boom", error_domain="domain-from-the-future")
        assert report.http_status == 500
