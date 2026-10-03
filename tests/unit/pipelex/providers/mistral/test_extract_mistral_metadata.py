"""Tests for ``extract_mistral_metadata``.

The helper distills a Mistral SDK exception into a ``ProviderErrorMetadata``
payload. Mistral's exception hierarchy differs from OpenAI/Anthropic:

- ``MistralError`` (base) carries ``status_code``, ``body`` (raw JSON string),
  ``headers`` (httpx.Headers), and ``raw_response``. The body is the raw
  response text, not a pre-parsed dict, so the helper JSON-parses it to
  recover ``provider_error_code``.
- ``NoResponseError`` is a separate ``Exception`` subclass with no response
  metadata; every status-related field must come back as ``None``.
"""

from __future__ import annotations

import httpx
from mistralai.client.errors import MistralError, NoResponseError

from pipelex.cogt.inference.error_classification import extract_mistral_metadata


def _make_response(status_code: int, headers: dict[str, str] | None = None, text: str = "") -> httpx.Response:
    request = httpx.Request("POST", "https://api.mistral.ai/v1/chat/completions")
    return httpx.Response(status_code=status_code, request=request, headers=headers or {}, text=text)


class TestExtractMistralMetadata:
    """``extract_mistral_metadata`` produces a populated payload for every SDK exception shape we care about."""

    def test_extracts_status_code_from_rate_limit_error(self) -> None:
        response = _make_response(
            429,
            headers={"x-request-id": "req_abc123"},
            text='{"message": "too many requests", "type": "rate_limit_error", "code": "rate_limit_exceeded"}',
        )
        exc = MistralError("rate limited", raw_response=response)

        metadata = extract_mistral_metadata(exc)

        assert metadata.provider == "mistral"
        assert metadata.sdk_exception_type == "MistralError"
        assert metadata.status_code == 429
        assert metadata.request_id == "req_abc123"

    def test_extracts_retry_after_seconds_when_header_present(self) -> None:
        response = _make_response(429, headers={"retry-after": "5"})
        exc = MistralError("rate limited", raw_response=response)

        metadata = extract_mistral_metadata(exc)

        assert metadata.retry_after_seconds == 5.0

    def test_retry_after_seconds_is_none_when_header_absent(self) -> None:
        response = _make_response(429)
        exc = MistralError("rate limited", raw_response=response)

        metadata = extract_mistral_metadata(exc)

        assert metadata.retry_after_seconds is None

    def test_extracts_provider_error_code_from_body_top_level(self) -> None:
        """Mistral's body is a raw JSON string; the helper parses it to recover error type/code."""
        body_text = '{"message": "missing field", "type": "invalid_request_error", "code": "missing_field"}'
        response = _make_response(400, text=body_text)
        exc = MistralError("bad input", raw_response=response)

        metadata = extract_mistral_metadata(exc)

        assert metadata.provider_error_code == "invalid_request_error"
        assert metadata.status_code == 400
        # body should be parsed into a dict for downstream consumers
        assert isinstance(metadata.body, dict)

    def test_extracts_provider_error_code_from_nested_error_section(self) -> None:
        """Mistral also returns ``{"error": {...}}`` style bodies on some endpoints."""
        body_text = '{"error": {"message": "bad", "type": "invalid_request_error"}}'
        response = _make_response(400, text=body_text)
        exc = MistralError("bad input", raw_response=response)

        metadata = extract_mistral_metadata(exc)

        assert metadata.provider_error_code == "invalid_request_error"

    def test_falls_back_to_code_when_type_is_absent(self) -> None:
        body_text = '{"message": "missing field", "code": "missing_field"}'
        response = _make_response(400, text=body_text)
        exc = MistralError("bad input", raw_response=response)

        metadata = extract_mistral_metadata(exc)

        assert metadata.provider_error_code == "missing_field"

    def test_handles_non_json_body_gracefully(self) -> None:
        """If the body is not JSON (e.g. an HTML error page), provider_error_code is None and body stays as the raw string."""
        response = _make_response(502, text="<html>Bad Gateway</html>")
        exc = MistralError("upstream error", raw_response=response)

        metadata = extract_mistral_metadata(exc)

        assert metadata.provider_error_code is None
        assert metadata.body == "<html>Bad Gateway</html>"
        assert metadata.status_code == 502

    def test_handles_no_response_error_without_status_code(self) -> None:
        """``NoResponseError`` carries neither status_code nor headers; every status-related field is None."""
        exc = NoResponseError("No response received")

        metadata = extract_mistral_metadata(exc)

        assert metadata.provider == "mistral"
        assert metadata.sdk_exception_type == "NoResponseError"
        assert metadata.status_code is None
        assert metadata.request_id is None
        assert metadata.retry_after_seconds is None
        assert metadata.provider_error_code is None

    def test_body_without_type_or_code_yields_none_provider_error_code(self) -> None:
        body_text = '{"message": "no error code here"}'
        response = _make_response(400, text=body_text)
        exc = MistralError("bad input", raw_response=response)

        metadata = extract_mistral_metadata(exc)

        assert metadata.provider_error_code is None

    def test_authentication_error_carries_status_code_401(self) -> None:
        body_text = '{"message": "Invalid API key", "type": "invalid_request_error", "code": "invalid_api_key"}'
        response = _make_response(401, headers={"x-request-id": "req_auth_xyz"}, text=body_text)
        exc = MistralError("Invalid API key", raw_response=response)

        metadata = extract_mistral_metadata(exc)

        assert metadata.status_code == 401
        assert metadata.request_id == "req_auth_xyz"
        assert metadata.provider_error_code == "invalid_request_error"

    def test_httpx_read_error_marked_as_network_error(self) -> None:
        """httpx.TransportError subclasses like ``ReadError`` should classify as network errors even though
        the class name does not contain ``timeout`` / ``connect`` / ``transport``.
        """
        exc = httpx.ReadError("connection reset")

        metadata = extract_mistral_metadata(exc)

        assert metadata.status_code is None
        assert metadata.is_network_error is True

    def test_httpx_remote_protocol_error_marked_as_network_error(self) -> None:
        exc = httpx.RemoteProtocolError("server disconnected")

        metadata = extract_mistral_metadata(exc)

        assert metadata.status_code is None
        assert metadata.is_network_error is True
