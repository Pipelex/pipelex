"""Tests for ``extract_huggingface_metadata``.

Distills an ``HfHubHTTPError`` / ``InferenceTimeoutError`` into a
``ProviderErrorMetadata``. HuggingFace mirrors the ``X-Request-Id`` header onto
``exc.request_id`` via ``HfHubHTTPError.__init__``.
"""

from __future__ import annotations

import httpx
from huggingface_hub.errors import HfHubHTTPError, InferenceTimeoutError

from pipelex.cogt.inference.error_classification import extract_huggingface_metadata


def _make_hf_http_error(status_code: int, headers: dict[str, str] | None = None, body_text: str = "") -> HfHubHTTPError:
    response = httpx.Response(
        status_code=status_code,
        headers=headers,
        text=body_text,
        request=httpx.Request("POST", "https://router.huggingface.co/test"),
    )
    return HfHubHTTPError(message=f"HTTP {status_code}", response=response)


class TestExtractHuggingFaceMetadata:
    """``extract_huggingface_metadata`` produces a populated payload for the shapes we care about."""

    def test_extracts_status_code_and_request_id(self) -> None:
        exc = _make_hf_http_error(429, headers={"x-request-id": "hf-req-1"})
        metadata = extract_huggingface_metadata(exc)

        assert metadata.provider == "huggingface"
        assert metadata.sdk_exception_type == "HfHubHTTPError"
        assert metadata.status_code == 429
        assert metadata.request_id == "hf-req-1"

    def test_falls_back_to_amzn_trace_id_header(self) -> None:
        exc = _make_hf_http_error(429, headers={"X-Amzn-Trace-Id": "amzn-trace-2"})
        metadata = extract_huggingface_metadata(exc)
        assert metadata.request_id == "amzn-trace-2"

    def test_extracts_retry_after_seconds(self) -> None:
        exc = _make_hf_http_error(429, headers={"retry-after": "10"})
        metadata = extract_huggingface_metadata(exc)
        assert metadata.retry_after_seconds == 10.0

    def test_extracts_provider_error_code_from_body(self) -> None:
        exc = _make_hf_http_error(
            400,
            body_text='{"error": {"code": "InvalidInput", "message": "bad"}}',
        )
        metadata = extract_huggingface_metadata(exc)
        assert metadata.provider_error_code == "InvalidInput"

    def test_html_body_falls_back_to_raw_string(self) -> None:
        exc = _make_hf_http_error(502, body_text="<html>bad gateway</html>")
        metadata = extract_huggingface_metadata(exc)
        assert metadata.status_code == 502
        assert metadata.provider_error_code is None
        assert isinstance(metadata.body, str)

    def test_unread_streaming_response_body_is_tolerated(self) -> None:
        """An unread streaming ``httpx.Response`` (hub 1.x async streaming error) must not crash the reader.

        Accessing ``.text`` on such a response raises ``httpx.ResponseNotRead``; the
        best-effort reader must swallow it and still return status/header metadata.
        """
        response = httpx.Response(
            status_code=503,
            headers={"x-request-id": "hf-req-stream", "retry-after": "7"},
            content=iter([b'{"error": "overloaded"}']),
            request=httpx.Request("POST", "https://router.huggingface.co/test"),
        )
        exc = HfHubHTTPError(message="HTTP 503", response=response)
        metadata = extract_huggingface_metadata(exc)
        assert metadata.status_code == 503
        assert metadata.request_id == "hf-req-stream"
        assert metadata.retry_after_seconds == 7.0
        assert metadata.body is None
        assert metadata.provider_error_code is None

    def test_inference_timeout_has_no_status(self) -> None:
        exc = InferenceTimeoutError("timed out")
        metadata = extract_huggingface_metadata(exc)
        assert metadata.provider == "huggingface"
        assert metadata.sdk_exception_type == "InferenceTimeoutError"
        assert metadata.status_code is None
        assert metadata.request_id is None
