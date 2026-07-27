"""Tests for ``extract_gateway_metadata``.

Distills a Portkey/Gateway SDK exception into a ``ProviderErrorMetadata``.
``APIStatusError`` subclasses carry ``status_code``, ``response`` (httpx),
and ``body`` (pre-parsed dict). ``APITimeoutError`` / ``APIConnectionError``
carry only a request; status fields come back as ``None``.
"""

from __future__ import annotations

import httpx
from portkey_ai.api_resources import exceptions as portkey_exc

from pipelex.cogt.inference.error_classification import extract_gateway_metadata


def _make_response(status_code: int, headers: dict[str, str] | None = None) -> httpx.Response:
    request = httpx.Request("POST", "https://api.portkey.ai/v1/chat/completions")
    return httpx.Response(status_code=status_code, request=request, headers=headers or {})


def _make_status_error(
    status_code: int,
    body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> portkey_exc.RateLimitError:
    request = httpx.Request("POST", "https://api.portkey.ai/v1/chat/completions")
    response = _make_response(status_code, headers)
    return portkey_exc.RateLimitError(message="error", request=request, response=response, body=body or {})


class TestExtractGatewayMetadata:
    """``extract_gateway_metadata`` produces a populated payload for every shape we care about."""

    def test_extracts_status_code_and_request_id(self) -> None:
        exc = _make_status_error(429, headers={"x-request-id": "gw-1"})
        metadata = extract_gateway_metadata(exc)

        assert metadata.provider == "gateway"
        assert metadata.sdk_exception_type == "RateLimitError"
        assert metadata.status_code == 429
        assert metadata.request_id == "gw-1"

    def test_falls_back_to_portkey_trace_id(self) -> None:
        exc = _make_status_error(429, headers={"x-portkey-trace-id": "trace-2"})
        metadata = extract_gateway_metadata(exc)
        assert metadata.request_id == "trace-2"

    def test_extracts_retry_after_seconds(self) -> None:
        exc = _make_status_error(429, headers={"retry-after": "9"})
        metadata = extract_gateway_metadata(exc)
        assert metadata.retry_after_seconds == 9.0

    def test_extracts_provider_error_code_from_body(self) -> None:
        exc = _make_status_error(400, body={"error": {"type": "invalid_request_error", "code": "missing_field"}})
        metadata = extract_gateway_metadata(exc)
        assert metadata.provider_error_code == "invalid_request_error"

    def test_handles_connection_error_without_response(self) -> None:
        request = httpx.Request("POST", "https://api.portkey.ai/v1/chat/completions")
        exc = portkey_exc.APIConnectionError(request=request)
        metadata = extract_gateway_metadata(exc)
        assert metadata.sdk_exception_type == "APIConnectionError"
        assert metadata.status_code is None
        assert metadata.request_id is None
