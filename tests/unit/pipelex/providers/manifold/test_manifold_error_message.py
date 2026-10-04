"""Which message `extract_manifold_metadata` reports for a failure on the manifold native routes.

`str()` of an `httpx.HTTPStatusError` is httpx's generic sentence, `Client error '401 Unauthorized'
for url …`, which never says why the service refused. The gateway and the native routes explain
themselves in the JSON body instead, so the message is read from there — the nested
`error.message` first, the top-level `message` second — and `str(exc)` is only the fallback for a
failure whose body carries neither.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from pipelex.providers.manifold.manifold_error_metadata import extract_manifold_metadata

_URL = "https://manifold.example.com/v1/pipelex/extract"
_HTTPX_SENTENCE = f"Client error '401 Unauthorized' for url '{_URL}'"
_GATEWAY_MESSAGE = "Portkey Error: Invalid API Key. Error Code: 03"


def _status_error(*, json_body: Any | None = None, text_body: str | None = None) -> httpx.HTTPStatusError:
    """A native-route refusal as the manifold client raises it: `raise_for_status()` on a plain httpx response."""
    request = httpx.Request("POST", _URL)
    if json_body is not None:
        response = httpx.Response(status_code=401, request=request, json=json_body)
    else:
        response = httpx.Response(status_code=401, request=request, text=text_body or "")
    return httpx.HTTPStatusError(_HTTPX_SENTENCE, request=request, response=response)


class TestTheMessageTheManifoldPathReports:
    def test_reports_the_gateways_own_message(self) -> None:
        """The body the gateway sends for a refused key, verbatim — its explanation is what reaches the user."""
        body = {"status": "failure", "message": _GATEWAY_MESSAGE, "error": {"message": _GATEWAY_MESSAGE, "code": "03"}}

        metadata = extract_manifold_metadata(_status_error(json_body=body))

        assert metadata.message == _GATEWAY_MESSAGE
        assert metadata.provider_error_code == "03"
        assert metadata.status_code == 401

    def test_prefers_the_nested_error_message_over_the_top_level_one(self) -> None:
        body = {"message": "top-level", "error": {"message": "nested", "code": "pig-01"}}

        metadata = extract_manifold_metadata(_status_error(json_body=body))

        assert metadata.message == "nested"

    def test_reads_the_top_level_message_when_the_error_object_has_none(self) -> None:
        body = {"message": "top-level", "error": {"code": "pig-01"}}

        metadata = extract_manifold_metadata(_status_error(json_body=body))

        assert metadata.message == "top-level"

    @pytest.mark.parametrize(
        ("topic", "json_body"),
        [
            ("no message anywhere", {"error": {"code": "pig-01"}}),
            ("a blank nested message and no top-level one", {"error": {"message": "  "}}),
            ("a null message", {"message": None}),
            ("a message that is not a string", {"error": {"message": 42}, "message": ["a"]}),
            ("a body that is not an object", ["unexpected"]),
        ],
    )
    def test_falls_back_to_the_exception_text_when_the_body_explains_nothing(self, topic: str, json_body: Any) -> None:
        metadata = extract_manifold_metadata(_status_error(json_body=json_body))

        assert metadata.message == _HTTPX_SENTENCE, topic

    def test_falls_back_to_the_exception_text_when_the_body_is_not_json(self) -> None:
        metadata = extract_manifold_metadata(_status_error(text_body="<html>Unauthorized</html>"))

        assert metadata.message == _HTTPX_SENTENCE
        assert metadata.body is None

    def test_a_request_error_keeps_its_own_text(self) -> None:
        """A connect or timeout failure has no response, hence no body to read a message from."""
        exc = httpx.ConnectError("connection refused", request=httpx.Request("POST", _URL))

        metadata = extract_manifold_metadata(exc)

        assert metadata.message == "connection refused"
        assert metadata.status_code is None
