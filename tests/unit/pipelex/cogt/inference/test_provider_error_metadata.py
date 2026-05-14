"""Tests for the ``ProviderErrorMetadata`` Pydantic model.

This model carries structured SDK metadata alongside every inference error so
downstream consumers (retry / temporal / CLI) do not have to scrape it back
from the exception chain.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipelex.cogt.inference.error_classification import ProviderErrorMetadata


class TestProviderErrorMetadata:
    """``ProviderErrorMetadata`` is a strict Pydantic model with two required fields and the rest optional."""

    def test_accepts_full_payload(self) -> None:
        metadata = ProviderErrorMetadata(
            provider="anthropic",
            sdk_exception_type="RateLimitError",
            status_code=429,
            request_id="req_abc123",
            retry_after_seconds=5.0,
            provider_error_code="rate_limit_error",
            body={"error": {"type": "rate_limit_error"}},
        )

        assert metadata.provider == "anthropic"
        assert metadata.sdk_exception_type == "RateLimitError"
        assert metadata.status_code == 429
        assert metadata.request_id == "req_abc123"
        assert metadata.retry_after_seconds == 5.0
        assert metadata.provider_error_code == "rate_limit_error"
        assert metadata.body == {"error": {"type": "rate_limit_error"}}

    def test_optional_fields_default_to_none(self) -> None:
        metadata = ProviderErrorMetadata(provider="anthropic", sdk_exception_type="APIConnectionError")

        assert metadata.status_code is None
        assert metadata.request_id is None
        assert metadata.retry_after_seconds is None
        assert metadata.provider_error_code is None
        assert metadata.body is None

    def test_provider_is_required(self) -> None:
        with pytest.raises(ValidationError):
            ProviderErrorMetadata(sdk_exception_type="RateLimitError")  # type: ignore[call-arg]

    def test_sdk_exception_type_is_required(self) -> None:
        with pytest.raises(ValidationError):
            ProviderErrorMetadata(provider="anthropic")  # type: ignore[call-arg]

    def test_round_trips_via_model_dump_and_validate(self) -> None:
        metadata = ProviderErrorMetadata(
            provider="anthropic",
            sdk_exception_type="RateLimitError",
            status_code=429,
            retry_after_seconds=5.0,
            body={"error": {"type": "rate_limit_error"}},
        )

        dumped = metadata.model_dump()
        rebuilt = ProviderErrorMetadata.model_validate(dumped)

        assert rebuilt == metadata
