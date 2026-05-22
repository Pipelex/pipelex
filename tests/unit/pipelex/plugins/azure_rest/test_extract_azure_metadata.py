"""Tests for ``extract_azure_metadata``.

Distills an ``httpx`` exception raised by an Azure REST call into a
``ProviderErrorMetadata``. Tolerates ``httpx.HTTPStatusError`` shapes (response
body is the raw JSON text the API returned) and connection/timeout shapes
(no response, every status field comes back as ``None``).
"""

from __future__ import annotations

import httpx

from pipelex.cogt.inference.error_classification import extract_azure_metadata


def _make_status_error(status_code: int, text: str = "", headers: dict[str, str] | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://test.openai.azure.com/openai/deployments/dall-e-3/images/generations")
    response = httpx.Response(status_code=status_code, request=request, text=text, headers=headers or {})
    return httpx.HTTPStatusError("error", request=request, response=response)


class TestExtractAzureMetadata:
    """``extract_azure_metadata`` produces a populated payload for the shapes we care about."""

    def test_extracts_status_code_and_request_id_from_status_error(self) -> None:
        exc = _make_status_error(
            429,
            text='{"error": {"code": "RateLimitReached", "message": "rate limited"}}',
            headers={"x-ms-request-id": "azure-req-1"},
        )
        metadata = extract_azure_metadata(exc)

        assert metadata.provider == "azure"
        assert metadata.sdk_exception_type == "HTTPStatusError"
        assert metadata.status_code == 429
        assert metadata.request_id == "azure-req-1"

    def test_falls_back_to_apim_request_id_header(self) -> None:
        exc = _make_status_error(
            429,
            text="{}",
            headers={"apim-request-id": "apim-req-2"},
        )
        metadata = extract_azure_metadata(exc)
        assert metadata.request_id == "apim-req-2"

    def test_extracts_retry_after_seconds(self) -> None:
        exc = _make_status_error(
            429,
            headers={"retry-after": "12"},
        )
        metadata = extract_azure_metadata(exc)
        assert metadata.retry_after_seconds == 12.0

    def test_extracts_provider_error_code_from_nested_error(self) -> None:
        exc = _make_status_error(
            400,
            text='{"error": {"code": "invalid_request_error", "message": "bad"}}',
        )
        metadata = extract_azure_metadata(exc)
        assert metadata.provider_error_code == "invalid_request_error"

    def test_extracts_provider_error_code_from_flat_body(self) -> None:
        exc = _make_status_error(
            400,
            text='{"code": "ContentFilter", "message": "blocked"}',
        )
        metadata = extract_azure_metadata(exc)
        assert metadata.provider_error_code == "ContentFilter"

    def test_html_error_body_falls_back_to_raw_string(self) -> None:
        exc = _make_status_error(
            502,
            text="<html><body>bad gateway</body></html>",
        )
        metadata = extract_azure_metadata(exc)
        assert metadata.status_code == 502
        assert metadata.provider_error_code is None
        assert isinstance(metadata.body, str)

    def test_handles_connect_error_without_response(self) -> None:
        request = httpx.Request("POST", "https://test.openai.azure.com/api")
        exc = httpx.ConnectError("Connection refused", request=request)

        metadata = extract_azure_metadata(exc)
        assert metadata.provider == "azure"
        assert metadata.sdk_exception_type == "ConnectError"
        assert metadata.status_code is None
        assert metadata.request_id is None
        assert metadata.body is None

    def test_handles_timeout_exception_without_response(self) -> None:
        exc = httpx.ReadTimeout("timed out")
        metadata = extract_azure_metadata(exc)
        assert metadata.sdk_exception_type == "ReadTimeout"
        assert metadata.status_code is None
