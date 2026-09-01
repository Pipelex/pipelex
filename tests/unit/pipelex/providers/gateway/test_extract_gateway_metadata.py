"""Tests for ``extract_gateway_metadata``.

Distills a Portkey/Gateway SDK exception into a ``ProviderErrorMetadata``.
``APIStatusError`` subclasses carry ``status_code``, ``response`` (httpx),
and ``body``. ``APITimeoutError`` / ``APIConnectionError`` carry only a
request; status fields come back as ``None``.

``body`` is a pre-parsed dict only on the paths that bypass Portkey's own
exception factory; the factory itself puts the message *string* there, so the
error code has to be recovered from the response. Both shapes are pinned below.
"""

from __future__ import annotations

import json

import httpx
from portkey_ai import Portkey
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


class TestTheCodeWhenPortkeyDiscardsThePayload:
    """``exc.body`` is not the payload on the SDK's own factory — the response still is."""

    @staticmethod
    def _as_the_sdk_raises_it(status_code: int, payload: dict[str, object]) -> BaseException:
        """Build the exception through Portkey's own factory, not through its constructor.

        The constructor accepts whatever ``body`` it is handed; only the factory
        reproduces the string ``body`` the Extract step actually receives.
        """
        request = httpx.Request("POST", "https://api.portkey.ai/v1/chat/completions")
        response = httpx.Response(
            status_code=status_code,
            request=request,
            content=json.dumps(payload).encode(),
            headers={"content-type": "application/json"},
        )
        client = Portkey(api_key="unused-in-this-test", base_url="https://api.portkey.ai/v1")
        return client._make_status_error_from_response(request=request, response=response)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    def test_the_code_is_recovered_from_the_response_body(self) -> None:
        """Portkey sets ``body`` to ``json.loads(text)["error"]["message"]`` — a string, not the document."""
        exc = self._as_the_sdk_raises_it(400, {"error": {"message": "refused", "code": "pig-11"}})

        assert isinstance(getattr(exc, "body", None), str)
        metadata = extract_gateway_metadata(exc)

        assert metadata.provider_error_code == "pig-11"
        assert isinstance(metadata.body, dict)

    def test_a_response_that_is_not_json_leaves_the_code_unset(self) -> None:
        request = httpx.Request("POST", "https://api.portkey.ai/v1/chat/completions")
        response = httpx.Response(status_code=502, request=request, content=b"<html>bad gateway</html>")
        exc = portkey_exc.APIStatusError(message="error", request=request, response=response, body=None)

        metadata = extract_gateway_metadata(exc)

        assert metadata.provider_error_code is None
        assert metadata.status_code == 502

    def test_a_dict_body_still_wins_over_the_response(self) -> None:
        """The vendored-OpenAI fallback paths hand a real dict here — it must not be re-parsed away."""
        exc = _make_status_error(400, body={"error": {"code": "pig-07"}})

        assert extract_gateway_metadata(exc).provider_error_code == "pig-07"
