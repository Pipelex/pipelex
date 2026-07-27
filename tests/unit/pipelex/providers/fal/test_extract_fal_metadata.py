"""Tests for ``extract_fal_metadata``.

Distills a ``FalClientHTTPError`` / ``FalClientTimeoutError`` / ``FalClientError`` /
``MissingCredentialsError`` into a ``ProviderErrorMetadata``.
"""

from __future__ import annotations

import httpx
from fal_client.auth import MissingCredentialsError
from fal_client.client import FalClientError, FalClientHTTPError, FalClientTimeoutError

from pipelex.cogt.inference.error_classification import extract_fal_metadata


def _make_fal_http_error(status_code: int, message: str = "", headers: dict[str, str] | None = None, body_text: str = "") -> FalClientHTTPError:
    request = httpx.Request("POST", "https://fal.ai/test")
    response = httpx.Response(status_code=status_code, request=request, text=body_text, headers=headers or {})
    return FalClientHTTPError(message=message, status_code=status_code, response_headers=headers or {}, response=response)


class TestExtractFalMetadata:
    """``extract_fal_metadata`` produces a populated payload for every FAL exception shape."""

    def test_extracts_status_code_and_request_id(self) -> None:
        exc = _make_fal_http_error(429, message="rate limited", headers={"x-request-id": "fal-req-1"})
        metadata = extract_fal_metadata(exc)

        assert metadata.provider == "fal"
        assert metadata.sdk_exception_type == "FalClientHTTPError"
        assert metadata.status_code == 429
        assert metadata.request_id == "fal-req-1"

    def test_extracts_retry_after_seconds(self) -> None:
        exc = _make_fal_http_error(429, headers={"retry-after": "8"})
        metadata = extract_fal_metadata(exc)
        assert metadata.retry_after_seconds == 8.0

    def test_extracts_provider_error_code_from_body(self) -> None:
        exc = _make_fal_http_error(
            400,
            body_text='{"error": {"code": "ContentPolicyViolation", "message": "blocked"}}',
        )
        metadata = extract_fal_metadata(exc)
        assert metadata.provider_error_code == "ContentPolicyViolation"

    def test_quota_402_carries_status_code(self) -> None:
        exc = _make_fal_http_error(402, message="payment required")
        metadata = extract_fal_metadata(exc)
        assert metadata.status_code == 402

    def test_timeout_error_has_no_status_or_request_id(self) -> None:
        exc = FalClientTimeoutError(timeout=30.0)
        metadata = extract_fal_metadata(exc)
        assert metadata.sdk_exception_type == "FalClientTimeoutError"
        assert metadata.status_code is None
        assert metadata.request_id is None

    def test_generic_client_error_has_no_status(self) -> None:
        exc = FalClientError("transient FAL error")
        metadata = extract_fal_metadata(exc)
        assert metadata.sdk_exception_type == "FalClientError"
        assert metadata.status_code is None

    def test_missing_credentials_has_no_status(self) -> None:
        exc = MissingCredentialsError()
        metadata = extract_fal_metadata(exc)
        assert metadata.sdk_exception_type == "MissingCredentialsError"
        assert metadata.status_code is None
