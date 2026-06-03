"""Tests for ``extract_anthropic_metadata``.

The helper distills an Anthropic SDK exception into a ``ProviderErrorMetadata``
payload. It must tolerate the SDK's two exception shapes:

- ``APIStatusError`` subclasses (e.g. ``RateLimitError``, ``BadRequestError``)
  carry ``status_code``, ``request_id``, ``response.headers``, ``body``.
- ``APIConnectionError`` / ``APITimeoutError`` only carry ``request`` and a
  ``message``; every status-related field must come back as ``None``.
"""

from __future__ import annotations

import anthropic
import httpx

from pipelex.cogt.inference.error_classification import extract_anthropic_metadata


def _make_response(status_code: int, headers: dict[str, str] | None = None) -> httpx.Response:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return httpx.Response(status_code=status_code, request=request, headers=headers or {})


class TestExtractAnthropicMetadata:
    """``extract_anthropic_metadata`` produces a populated payload for every SDK exception shape we care about."""

    def test_extracts_status_code_and_request_id_from_rate_limit_error(self) -> None:
        exc = anthropic.RateLimitError(
            "rate limited",
            response=_make_response(429, headers={"request-id": "req_abc123"}),
            body={"error": {"type": "rate_limit_error", "message": "too many requests"}},
        )

        metadata = extract_anthropic_metadata(exc)

        assert metadata.provider == "anthropic"
        assert metadata.sdk_exception_type == "RateLimitError"
        assert metadata.status_code == 429
        assert metadata.request_id == "req_abc123"
        assert metadata.provider_error_code == "rate_limit_error"
        assert metadata.body == {"error": {"type": "rate_limit_error", "message": "too many requests"}}

    def test_extracts_retry_after_seconds_when_header_present(self) -> None:
        exc = anthropic.RateLimitError(
            "rate limited",
            response=_make_response(429, headers={"retry-after": "5"}),
            body=None,
        )

        metadata = extract_anthropic_metadata(exc)

        assert metadata.retry_after_seconds == 5.0

    def test_retry_after_seconds_is_none_when_header_absent(self) -> None:
        exc = anthropic.RateLimitError(
            "rate limited",
            response=_make_response(429),
            body=None,
        )

        metadata = extract_anthropic_metadata(exc)

        assert metadata.retry_after_seconds is None

    def test_extracts_provider_error_code_from_body(self) -> None:
        exc = anthropic.BadRequestError(
            "bad input",
            response=_make_response(400),
            body={"error": {"type": "invalid_request_error", "message": "missing field"}},
        )

        metadata = extract_anthropic_metadata(exc)

        assert metadata.provider_error_code == "invalid_request_error"
        assert metadata.status_code == 400

    def test_handles_connection_error_without_response(self) -> None:
        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        exc = anthropic.APIConnectionError(message="Connection refused", request=request)

        metadata = extract_anthropic_metadata(exc)

        assert metadata.provider == "anthropic"
        assert metadata.sdk_exception_type == "APIConnectionError"
        assert metadata.status_code is None
        assert metadata.request_id is None
        assert metadata.retry_after_seconds is None
        assert metadata.provider_error_code is None

    def test_handles_timeout_error_without_response(self) -> None:
        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        exc = anthropic.APITimeoutError(request=request)

        metadata = extract_anthropic_metadata(exc)

        assert metadata.sdk_exception_type == "APITimeoutError"
        assert metadata.status_code is None
        assert metadata.retry_after_seconds is None

    def test_body_without_error_type_yields_none_provider_error_code(self) -> None:
        exc = anthropic.BadRequestError(
            "bad input",
            response=_make_response(400),
            body={"unrelated": "shape"},
        )

        metadata = extract_anthropic_metadata(exc)

        assert metadata.provider_error_code is None
        assert metadata.body == {"unrelated": "shape"}
