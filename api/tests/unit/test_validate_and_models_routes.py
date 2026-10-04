"""Smoke + validation tests for /validate and /models."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mthds.protocol.models import ModelCategory as MthdsModelCategory
from pipelex.cogt.models.model_listing import ModelCategory
from pipelex.interpreter_hub import get_library_manager
from pytest_mock import MockerFixture

from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router
from tests.unit._constants import VALID_MTHDS


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


class TestValidateAndModelsRoutes:
    def test_validate_rejects_oversized_mthds(self):
        client = _build_client()
        oversized = "a" * (2 * 1024 * 1024)  # 2 MiB > 1 MiB cap
        response = client.post(
            "/v1/validate",
            json={"mthds_contents": [oversized]},
        )
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "ValidationError"

    def test_validate_rejects_too_many_files(self):
        client = _build_client()
        response = client.post(
            "/v1/validate",
            json={"mthds_contents": [VALID_MTHDS] * 32},
        )
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "ValidationError"

    def test_validate_invalid_mthds_returns_200_invalid_report(self):
        # `/validate` is a diagnostic endpoint: an invalid bundle is a produced verdict, so it rides
        # a 200 `InvalidReport` (discriminated on `is_valid: false`) — NOT a 422 problem document,
        # and NOT the older `{success, mthds_contents, message}` 422 envelope. Invalid TOML reliably
        # triggers a `ValidateBundleError` from the interpreter, which the route converts to the
        # invalid arm. The verdict is carried by `is_valid`/`message`, not the status code.
        client = _build_client()
        response = client.post(
            "/v1/validate",
            json={"mthds_contents": ["this is not valid TOML !!!"]},
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("application/json")
        body = response.json()
        assert body["is_valid"] is False
        assert body["is_runnable"] is False
        # The pipelex message is preserved (caller-facing under `_authors_caller_facing_message`) so
        # the client gets the actual interpreter complaint, not a generic placeholder.
        assert "TOML" in body["message"]
        # The diagnostics list is non-empty on every invalid arm — the structured-info invariant is
        # total. A raw TOML-syntax error is a parse-level failure the interpreter raises with no
        # categorized error-data, but the shared builder's last-resort residual still emits one
        # `blueprint_validation` item carrying the message (no `source` at this layer). A categorized
        # failure (e.g. an invalid `main_pipe`) yields richer items; that path is pinned in
        # test_validate_errors.py.
        assert isinstance(body["validation_errors"], list)
        assert body["validation_errors"], "an invalid verdict must carry a non-empty validation_errors[]"
        assert body["validation_errors"][0]["category"] == "blueprint_validation"
        assert body["validation_errors"][0]["message"]
        # The valid arm's structural artifacts + the retired `success` extra are absent.
        assert "bundle_blueprint" not in body
        assert "success" not in body

    # NOTE: the former `main_pipe` precondition on /validate is deleted (protocol alignment
    # D2) — a bundle without `main_pipe` now answers 200 with `graph_spec=null`. The
    # regression pin for that behavior (both backends) lives in `test_validate_envelope.py`.

    @pytest.mark.parametrize("bad_type", ["not-a-real-category", ""])
    def test_models_rejects_invalid_category(self, bad_type: str):
        # The empty string is an explicitly-supplied (invalid) filter value, not an absent
        # param — it must fail loudly like any other unknown category, not silently return
        # the unfiltered deck.
        client = _build_client()
        response = client.get(f"/v1/models?type={bad_type}")
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "InvalidModelCategory"

    def test_models_rejects_repeated_type_param(self):
        # D11: the protocol's `type` filter is a single plain value. The old route accepted
        # repeated `?type=` values (list[str] Query) — that extension is dropped, and FastAPI
        # would otherwise silently keep one of the values, so the rejection is explicit.
        # Generic ValidationError (not InvalidModelCategory): both values are valid
        # categories — what's wrong is the arity.
        client = _build_client()
        response = client.get("/v1/models?type=llm&type=extract")
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "ValidationError"

    def test_models_returns_protocol_deck(self):
        # The deck is the protocol `ModelDeck` shape produced by `PipelexMTHDSProtocol.models`:
        # a non-empty flat `models` list (regression for the silently-empty deck the old raw
        # per-category payload caused in the SDK — F2) plus this implementation's routing
        # extensions, keyed by category (the same alias name exists in several categories —
        # a flat map would silently drop entries on collision). The old raw keys (`presets`
        # by category, `success`) are gone. Every entry of the flat list is typed by one of the
        # protocol's categories, `judgment` among them, and never by a value the protocol does not
        # define; the extensions are keyed by the categories this runtime serves.
        client = _build_client()
        response = client.get("/v1/models")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["models"], "the protocol deck must carry a non-empty models list"
        first_model = body["models"][0]
        assert first_model["name"]
        assert first_model["type"]
        assert {model["type"] for model in body["models"]} <= {category.value for category in MthdsModelCategory}
        valid_categories = {category.value for category in ModelCategory}
        assert set(body["aliases"]) <= valid_categories
        assert all(isinstance(category_aliases, dict) for category_aliases in body["aliases"].values())
        assert set(body["waterfalls"]) <= valid_categories
        assert "presets" not in body
        assert "success" not in body

    def test_models_single_type_filter(self):
        client = _build_client()
        response = client.get("/v1/models?type=llm")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["models"]
        assert {model["type"] for model in body["models"]} == {"llm"}
        assert set(body["aliases"]) <= {"llm"}

    def test_empty_mthds_contents_rejected(self):
        # `/validate` is the last route on the `mthds_contents` envelope (it is protocol-owned; the
        # crate routes take `files[]`, whose empty-selector rejection is pinned in the pipe-io suite).
        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": []})
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["error_type"] == "ValidationError"

    def test_validate_tears_down_validate_bundle_library_without_leaking(self, mocker: MockerFixture):
        # validate_bundle opens a library and leaves it loaded + current on success (the D6 contract);
        # /validate must own that teardown. Before the fix the route never tore it down, orphaning it on
        # every successful call (the best-effort graph dry-run opens + tears down its OWN library via
        # PipelexRunner, so that one was balanced). Assert the conservation property: every library opened
        # during the request is torn down — open count == teardown count. A leak shows up as opens > teardowns.
        library_manager = get_library_manager()
        open_spy = mocker.spy(library_manager, "open_library")
        teardown_spy = mocker.spy(library_manager, "teardown")

        client = _build_client()
        response = client.post("/v1/validate", json={"mthds_contents": [VALID_MTHDS]})

        assert response.status_code == 200, response.text
        assert open_spy.call_count >= 1
        assert open_spy.call_count == teardown_spy.call_count
