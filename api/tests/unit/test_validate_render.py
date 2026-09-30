"""`/validate` opt-in `rendered_markdown` extra (D-D) — a Pipelex-API presentation layer.

The neutral 200 verdict body is unchanged by default; when the request's `render` includes the
supported `markdown` token, the response gains a `rendered_markdown` field on BOTH 200 arms (valid
and invalid). An unknown/unsupported token is silently ignored (lenient-ignore, NOT a 422) because
`render` is a presentation hint, not part of the verdict contract. The markdown is rendered
server-side by the shared pipelex renderers (`format_validate_markdown` / `render_invalid_validation_markdown`),
so the API and the local CLI cannot drift in format/structure.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.exception_handlers import register_exception_handlers
from api.routes import router as api_router
from tests.unit._constants import INVALID_MAIN_PIPE_MTHDS, VALID_MTHDS


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


class TestValidateRenderedMarkdown:
    def test_default_request_has_no_rendered_markdown(self):
        # Off by default: the response is the plain structured verdict, byte-parity with today.
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        assert "rendered_markdown" not in body

    def test_markdown_requested_valid_arm_carries_rendered_markdown(self):
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS], "render": ["markdown"]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        assert body["rendered_markdown"].startswith("# Validation passed")
        # The view rides alongside the structured fields, which remain the contract.
        assert "validated_pipes" in body

    def test_markdown_requested_invalid_arm_carries_rendered_markdown(self):
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [INVALID_MAIN_PIPE_MTHDS], "render": ["markdown"]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        assert body["rendered_markdown"].startswith("# Validation failed")
        # The structured verdict is still present; markdown is the view, not a replacement.
        assert body["validation_errors"]

    def test_invalid_arm_without_render_has_no_rendered_markdown(self):
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [INVALID_MAIN_PIPE_MTHDS]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        assert "rendered_markdown" not in body

    def test_unknown_render_token_is_ignored_not_422(self):
        # Lenient-ignore: an unsupported token yields the 200 verdict with NO rendered field —
        # the one place the request-shape-422 contract deliberately does not apply.
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS], "render": ["bogus"]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        assert "rendered_markdown" not in body

    def test_mixed_known_and_unknown_tokens_render_the_known_one(self):
        # Per-token resolution: a known token renders, the unknown one is dropped (not poisoning).
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS], "render": ["markdown", "bogus"]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["rendered_markdown"].startswith("# Validation passed")
