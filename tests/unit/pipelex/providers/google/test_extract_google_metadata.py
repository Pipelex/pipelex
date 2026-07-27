"""Tests for ``extract_google_metadata``.

The helper distills a Google GenAI SDK exception (``ClientError`` /
``ServerError`` / ``APIError``) into a ``ProviderErrorMetadata`` payload.

Google's exception shape differs from OpenAI/Anthropic:

- Status code lives on ``exc.code`` (an ``int``), not ``exc.status_code``.
- The response body lives on ``exc.details`` (whatever JSON dict the API
  returned), not ``exc.body``.
- The wrapped response object may be ``None``, ``httpx.Response``, or a
  ``requests.Response``; ``request_id`` / ``retry_after`` come from
  ``response.headers`` when available.
- Google's error payload uses ``{"error": {"status": "RESOURCE_EXHAUSTED",
  ...}}`` for the provider error code (status string, not numeric).
"""

from __future__ import annotations

import httpx
from google.genai import errors as genai_errors

from pipelex.cogt.inference.error_classification import extract_google_metadata


def _make_response(status_code: int, headers: dict[str, str] | None = None) -> httpx.Response:
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent")
    return httpx.Response(status_code=status_code, request=request, headers=headers or {})


class TestExtractGoogleMetadata:
    """``extract_google_metadata`` produces a populated payload for every SDK exception shape we care about."""

    def test_extracts_status_code_from_client_error(self) -> None:
        response_json = {
            "error": {
                "code": 429,
                "message": "Resource has been exhausted",
                "status": "RESOURCE_EXHAUSTED",
            },
        }
        response = _make_response(429, headers={"x-goog-request-id": "req_abc123"})
        exc = genai_errors.ClientError(429, response_json, response)

        metadata = extract_google_metadata(exc)

        assert metadata.provider == "google"
        assert metadata.sdk_exception_type == "ClientError"
        assert metadata.status_code == 429
        assert metadata.request_id == "req_abc123"

    def test_extracts_retry_after_seconds_when_header_present(self) -> None:
        response = _make_response(429, headers={"retry-after": "10"})
        exc = genai_errors.ClientError(429, {"message": "rate limited"}, response)

        metadata = extract_google_metadata(exc)

        assert metadata.retry_after_seconds == 10.0

    def test_retry_after_seconds_is_none_when_header_absent(self) -> None:
        response = _make_response(429)
        exc = genai_errors.ClientError(429, {"message": "rate limited"}, response)

        metadata = extract_google_metadata(exc)

        assert metadata.retry_after_seconds is None

    def test_extracts_provider_error_code_from_nested_error_status(self) -> None:
        """Google's standard payload uses ``error.status`` for the symbolic error code."""
        response_json = {
            "error": {
                "code": 429,
                "message": "Quota exceeded",
                "status": "RESOURCE_EXHAUSTED",
            },
        }
        exc = genai_errors.ClientError(429, response_json, _make_response(429))

        metadata = extract_google_metadata(exc)

        assert metadata.provider_error_code == "RESOURCE_EXHAUSTED"

    def test_extracts_provider_error_code_from_top_level_status(self) -> None:
        """Some Google error payloads put ``status`` at the top level instead of inside ``error``."""
        response_json = {"message": "Permission denied", "status": "PERMISSION_DENIED"}
        exc = genai_errors.ClientError(403, response_json, _make_response(403))

        metadata = extract_google_metadata(exc)

        assert metadata.provider_error_code == "PERMISSION_DENIED"

    def test_body_is_the_response_details(self) -> None:
        response_json = {
            "error": {"code": 400, "message": "Invalid argument", "status": "INVALID_ARGUMENT"},
        }
        exc = genai_errors.ClientError(400, response_json, _make_response(400))

        metadata = extract_google_metadata(exc)

        assert metadata.body == response_json

    def test_handles_server_error_with_status_code_500(self) -> None:
        response_json = {"error": {"code": 500, "message": "Internal error", "status": "INTERNAL"}}
        exc = genai_errors.ServerError(500, response_json, _make_response(500))

        metadata = extract_google_metadata(exc)

        assert metadata.provider == "google"
        assert metadata.sdk_exception_type == "ServerError"
        assert metadata.status_code == 500
        assert metadata.provider_error_code == "INTERNAL"

    def test_handles_none_response_gracefully(self) -> None:
        """When the SDK constructs an error without a response object, status-related fields fall back."""
        response_json = {"error": {"code": 400, "message": "Bad request", "status": "INVALID_ARGUMENT"}}
        exc = genai_errors.ClientError(400, response_json, None)

        metadata = extract_google_metadata(exc)

        assert metadata.provider == "google"
        assert metadata.sdk_exception_type == "ClientError"
        assert metadata.status_code == 400
        assert metadata.request_id is None
        assert metadata.retry_after_seconds is None
        assert metadata.provider_error_code == "INVALID_ARGUMENT"

    def test_body_without_error_or_status_yields_none_provider_error_code(self) -> None:
        response_json = {"message": "no status field"}
        exc = genai_errors.ClientError(400, response_json, _make_response(400))

        metadata = extract_google_metadata(exc)

        assert metadata.provider_error_code is None

    def test_authentication_error_carries_status_code_401(self) -> None:
        response_json = {
            "error": {
                "code": 401,
                "message": "Request had invalid authentication credentials",
                "status": "UNAUTHENTICATED",
            },
        }
        response = _make_response(401, headers={"x-goog-request-id": "req_auth_xyz"})
        exc = genai_errors.ClientError(401, response_json, response)

        metadata = extract_google_metadata(exc)

        assert metadata.status_code == 401
        assert metadata.request_id == "req_auth_xyz"
        assert metadata.provider_error_code == "UNAUTHENTICATED"

    def test_httpx_read_error_marked_as_network_error(self) -> None:
        """httpx.TransportError subclasses like ``ReadError`` should classify as network errors even though
        the class name does not contain ``timeout`` / ``connect`` / ``transport``.
        """
        exc = httpx.ReadError("connection reset")

        metadata = extract_google_metadata(exc)

        assert metadata.status_code is None
        assert metadata.is_network_error is True

    def test_httpx_remote_protocol_error_marked_as_network_error(self) -> None:
        exc = httpx.RemoteProtocolError("server disconnected")

        metadata = extract_google_metadata(exc)

        assert metadata.status_code is None
        assert metadata.is_network_error is True
