"""Tests for ``extract_openai_metadata``.

The helper distills an OpenAI SDK exception into a ``ProviderErrorMetadata``
payload. It must tolerate the SDK's two exception shapes:

- ``APIStatusError`` subclasses (e.g. ``RateLimitError``, ``BadRequestError``)
  carry ``status_code``, ``request_id`` (from ``x-request-id`` header),
  ``response.headers``, and ``body`` (already pre-unwrapped by the SDK so
  ``body["type"]`` / ``body["code"]`` sit at the top level).
- ``APIConnectionError`` / ``APITimeoutError`` only carry ``request`` and a
  ``message``; every status-related field must come back as ``None``.
"""

from __future__ import annotations

import httpx
import openai

from pipelex.cogt.inference.error_classification import extract_openai_metadata


def _make_response(status_code: int, headers: dict[str, str] | None = None) -> httpx.Response:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return httpx.Response(status_code=status_code, request=request, headers=headers or {})


class TestExtractOpenAIMetadata:
    """``extract_openai_metadata`` produces a populated payload for every SDK exception shape we care about."""

    def test_extracts_status_code_and_request_id_from_rate_limit_error(self) -> None:
        exc = openai.RateLimitError(
            "rate limited",
            response=_make_response(429, headers={"x-request-id": "req_abc123"}),
            body={"type": "rate_limit_error", "code": "rate_limit_exceeded", "message": "too many requests"},
        )

        metadata = extract_openai_metadata(exc)

        assert metadata.provider == "openai"
        assert metadata.sdk_exception_type == "RateLimitError"
        assert metadata.status_code == 429
        assert metadata.request_id == "req_abc123"

    def test_extracts_retry_after_seconds_when_header_present(self) -> None:
        exc = openai.RateLimitError(
            "rate limited",
            response=_make_response(429, headers={"retry-after": "5"}),
            body=None,
        )

        metadata = extract_openai_metadata(exc)

        assert metadata.retry_after_seconds == 5.0

    def test_retry_after_seconds_is_none_when_header_absent(self) -> None:
        exc = openai.RateLimitError(
            "rate limited",
            response=_make_response(429),
            body=None,
        )

        metadata = extract_openai_metadata(exc)

        assert metadata.retry_after_seconds is None

    def test_extracts_provider_error_code_from_type_attribute(self) -> None:
        """OpenAI SDK pre-unwraps ``body["error"]`` into ``exc.type`` / ``exc.code``."""
        exc = openai.BadRequestError(
            "bad input",
            response=_make_response(400),
            body={"type": "invalid_request_error", "code": "missing_field", "message": "missing field"},
        )

        metadata = extract_openai_metadata(exc)

        assert metadata.provider_error_code == "invalid_request_error"
        assert metadata.status_code == 400

    def test_falls_back_to_code_when_type_is_absent(self) -> None:
        exc = openai.BadRequestError(
            "bad input",
            response=_make_response(400),
            body={"code": "missing_field", "message": "missing field"},
        )

        metadata = extract_openai_metadata(exc)

        assert metadata.provider_error_code == "missing_field"

    def test_handles_connection_error_without_response(self) -> None:
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        exc = openai.APIConnectionError(message="Connection refused", request=request)

        metadata = extract_openai_metadata(exc)

        assert metadata.provider == "openai"
        assert metadata.sdk_exception_type == "APIConnectionError"
        assert metadata.status_code is None
        assert metadata.request_id is None
        assert metadata.retry_after_seconds is None
        assert metadata.provider_error_code is None

    def test_handles_timeout_error_without_response(self) -> None:
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        exc = openai.APITimeoutError(request=request)

        metadata = extract_openai_metadata(exc)

        assert metadata.sdk_exception_type == "APITimeoutError"
        assert metadata.status_code is None
        assert metadata.retry_after_seconds is None

    def test_body_without_type_or_code_yields_none_provider_error_code(self) -> None:
        exc = openai.BadRequestError(
            "bad input",
            response=_make_response(400),
            body={"message": "no error code"},
        )

        metadata = extract_openai_metadata(exc)

        assert metadata.provider_error_code is None

    def test_authentication_error_carries_status_code_401(self) -> None:
        exc = openai.AuthenticationError(
            "Invalid API key",
            response=_make_response(401, headers={"x-request-id": "req_auth_xyz"}),
            body={"type": "invalid_request_error", "code": "invalid_api_key"},
        )

        metadata = extract_openai_metadata(exc)

        assert metadata.status_code == 401
        assert metadata.sdk_exception_type == "AuthenticationError"
        assert metadata.request_id == "req_auth_xyz"
        assert metadata.provider_error_code == "invalid_request_error"

    def test_not_found_error_carries_status_code_404(self) -> None:
        exc = openai.NotFoundError(
            "Model not found",
            response=_make_response(404),
            body={"type": "invalid_request_error", "code": "model_not_found"},
        )

        metadata = extract_openai_metadata(exc)

        assert metadata.status_code == 404
        assert metadata.sdk_exception_type == "NotFoundError"
