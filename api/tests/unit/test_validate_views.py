"""`/validate` opt-in `input_form` structured view (D-D) — the `views` axis.

The second opt-in axis beside `render`, with identical mechanics and a different product: `render`
yields *rendered text* under a mechanical `rendered_<format>` key, a view attaches a *structured*
artifact under a **same-named** top-level field. The canonical `PipelexValidationReport` always
carries `input_form` (required there, so a backend that forgets to derive it fails loudly), which is
exactly why the wire gate has to be an explicit pop rather than a serialization side effect: the
field is a populated dict, not a `None` that `exclude_none` would drop.

What is pinned here: absent by default on both 200 arms (so the high-frequency callers — hook
pipelines, CI gates, agent loops — never pay for a form they discard); present on the valid arm when
the token is requested, keyed exactly like `pipe_io_contracts`; never on the invalid arm, whose
crate was never assembled; unknown tokens lenient-ignored rather than 422'd; and `views` / `render`
resolving independently.
"""

from typing import Any

import pytest
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


class TestValidateInputFormView:
    def test_default_request_has_no_input_form(self):
        # Off by default: the valid arm stays byte-lean, carrying the structured contract only.
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        assert "input_form" not in body, f"`input_form` must be absent by default, got keys: {sorted(body)}"
        # The facts the view projects are still there — the view is opt-in, the contract is not.
        assert "pipe_io_contracts" in body

    def test_empty_views_list_has_no_input_form(self):
        # An explicit empty list is the same as omitting the field — no view, no field.
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS], "views": []})
        assert response.status_code == 200, response.text
        assert "input_form" not in response.json()

    def test_input_form_requested_valid_arm_carries_the_view(self):
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS], "views": ["input_form"]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        input_form: dict[str, Any] = body["input_form"]
        # Keyed exactly like `pipe_io_contracts` — the namespaced `pipe_ref`, same set.
        assert set(input_form) == set(body["pipe_io_contracts"]), (
            f"`input_form` must map the same pipe_ref keys as `pipe_io_contracts`, got {sorted(input_form)} vs {sorted(body['pipe_io_contracts'])}"
        )
        descriptor = input_form["smoke.echo"]
        field_names = [field["name"] for field in descriptor["fields"]]
        assert field_names == ["text"], f"The descriptor states the pipe's authored inputs, got {field_names}"

    def test_duplicate_token_is_deduped_not_an_error(self):
        # Resolved as a set: order-insensitive and deduped, so a repeated token is inert.
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS], "views": ["input_form", "input_form"]})
        assert response.status_code == 200, response.text
        assert "input_form" in response.json()

    def test_invalid_arm_without_views_has_no_input_form(self):
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [INVALID_MAIN_PIPE_MTHDS]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        assert "input_form" not in body

    def test_invalid_arm_never_carries_input_form_even_when_requested(self):
        # The descriptor derives from a crate that does not exist when load/parse/wiring failed, so
        # it follows `bundle_blueprint` / `pipe_io_contracts` / `graph_spec` into absence here.
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [INVALID_MAIN_PIPE_MTHDS], "views": ["input_form"]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is False
        assert "input_form" not in body, f"The invalid arm never carries `input_form`, got keys: {sorted(body)}"
        assert body["validation_errors"]

    def test_unknown_view_token_is_ignored_not_422(self):
        # Lenient-ignore: a stale view token must never fail the call.
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS], "views": ["bogus"]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_valid"] is True
        assert "input_form" not in body

    @pytest.mark.parametrize("views", [["bogus", "input_form"], ["input_form", "bogus"]], ids=["unknown_first", "known_first"])
    def test_mixed_known_and_unknown_tokens_attach_the_known_one(self, views: list[str]):
        # Per-token resolution: the known token attaches, the unknown one is dropped (not poisoning).
        # Both orders, since the tokens resolve as a set — position must not decide the outcome.
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS], "views": views})
        assert response.status_code == 200, response.text
        assert "input_form" in response.json()

    def test_no_verdict_422_carries_no_input_form(self):
        # No verdict, no view: a request-shape 422 is an RFC 7807 problem document, nothing else.
        client = _build_client()
        response = client.post(
            "/v1/validate",
            json={"mthds_contents": [VALID_MTHDS], "mthds_sources": ["a.mthds", "b.mthds"], "views": ["input_form"]},
        )
        assert response.status_code == 422, response.text
        assert "input_form" not in response.json()


class TestViewsAndRenderAreIndependent:
    """The two opt-in lists resolve their own tokens against their own supported sets."""

    def test_render_alone_does_not_attach_the_view(self):
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS], "render": ["markdown"]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["rendered_markdown"].startswith("# Validation passed")
        assert "input_form" not in body

    def test_views_alone_does_not_render(self):
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS], "views": ["input_form"]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert "input_form" in body
        assert "rendered_markdown" not in body

    def test_both_lists_populate_their_own_fields(self):
        client = _build_client()
        response = client.post(
            "/v1/validate",
            json={"mthds_contents": [VALID_MTHDS], "render": ["markdown"], "views": ["input_form"]},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["rendered_markdown"].startswith("# Validation passed")
        assert "input_form" in body

    def test_tokens_do_not_cross_axes(self):
        # `input_form` is not a render format and `markdown` is not a view: each is unknown to the
        # other list, and an unknown token is dropped rather than 422'd.
        client = _build_client()
        response = client.post(
            "/v1/validate",
            json={"mthds_contents": [VALID_MTHDS], "render": ["input_form"], "views": ["markdown"]},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert "rendered_markdown" not in body
        assert "input_form" not in body
