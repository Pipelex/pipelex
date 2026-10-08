"""The model reference check route, `GET /v1/models/check`, on the server's own deck."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router
from pipelex_api.routes.pipelex.agent.models import MAX_MODEL_REFERENCE_LENGTH

_CHECK_PATH = "/v1/models/check"

_VERDICT_FIELDS = {"reference", "kind", "name", "category", "resolution", "matches", "suggestions", "other_kinds", "other_categories"}


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    return TestClient(app)


def _verdict(client: TestClient, params: list[tuple[str, str]]) -> dict[str, Any]:
    response = client.get(_CHECK_PATH, params=tuple(params))
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")
    verdict: dict[str, Any] = response.json()
    assert set(verdict) == _VERDICT_FIELDS
    return verdict


def _img_gen_bundle(*, model: str) -> str:
    return f"""
domain      = "harbour_board"
description = "Draw the board announcing the tide times"
main_pipe   = "draw_tide_board"

[pipe.draw_tide_board]
type        = "PipeImgGen"
description = "Draw the painted board announcing the tide times"
output      = "Image"
model       = "{model}"
prompt      = "A painted wooden harbour board announcing the tide times, morning light"
"""


class TestModelsCheckRoute:
    def test_a_preset_of_the_deck_resolves_in_its_category(self):
        client = _build_client()
        preset = client.get("/v1/models").json()["models"][0]

        verdict = _verdict(client, [("reference", f"${preset['name']}"), ("type", preset["type"])])

        assert verdict["resolution"] == "resolved"
        assert verdict["kind"] == "preset"
        assert verdict["name"] == preset["name"]
        assert verdict["category"] == preset["type"]
        (match,) = verdict["matches"]
        assert set(match) == {"category", "resolves_to", "target", "description"}
        assert match["category"] == preset["type"]
        assert verdict["suggestions"] == verdict["other_kinds"] == verdict["other_categories"] == []

    def test_an_alias_and_its_target_resolve_with_the_alias_in_via(self):
        client = _build_client()
        alias_name, alias_target = next(iter(client.get("/v1/models", params={"type": "llm"}).json()["aliases"]["llm"].items()))

        alias_verdict = _verdict(client, [("reference", f"  alias:{alias_name} "), ("type", "llm")])
        handle_verdict = _verdict(client, [("reference", alias_target), ("type", "llm")])

        assert alias_verdict["reference"] == f"alias:{alias_name}"
        assert alias_verdict["matches"] == [{"category": "llm", "resolves_to": alias_target, "target": alias_target}]
        assert handle_verdict["resolution"] == "resolved"
        assert handle_verdict["kind"] == "handle"
        (match,) = handle_verdict["matches"]
        assert match["resolves_to"] == alias_target
        assert f"@{alias_name}" in match["via"]

    def test_an_llm_asked_as_an_image_generation_model_is_not_found_and_fails_validation_too(self):
        """The check and a validation agree: an LLM the deck serves is neither checked nor validated as an image-generation model."""
        client = _build_client()
        llm_handle = next(iter(client.get("/v1/models", params={"type": "llm"}).json()["aliases"]["llm"].values()))

        verdict = _verdict(client, [("reference", llm_handle), ("type", "img_gen")])
        validation = client.post("/v1/validate", json={"mthds_contents": [_img_gen_bundle(model=llm_handle)]})

        assert verdict["resolution"] == "not_found"
        assert verdict["matches"] == []
        assert verdict["other_categories"] == ["llm"]
        assert validation.status_code == 200, validation.text
        report = validation.json()
        assert report["is_valid"] is False
        (item,) = report["validation_errors"]
        assert item["error_type"] == "unknown_model"
        assert item["model_reference"] == llm_handle
        assert item["model_type"] == "img_gen"
        assert "but not as an image-generation model" in item["message"]

    def test_doc_gen_is_a_category_of_the_check(self):
        client = _build_client()

        verdict = _verdict(client, [("reference", "$no-preset-is-named-this"), ("type", "doc_gen")])

        assert verdict["category"] == "doc_gen"
        assert verdict["resolution"] == "not_found"

    def test_the_longest_accepted_reference_is_a_verdict(self):
        client = _build_client()

        verdict = _verdict(client, [("reference", "@" + "x" * (MAX_MODEL_REFERENCE_LENGTH - 1))])

        assert verdict["resolution"] == "not_found"
        assert verdict["category"] is None

    @pytest.mark.parametrize(
        ("params", "error_type"),
        [
            pytest.param([], "ValidationError", id="reference-missing"),
            pytest.param([("reference", "@a"), ("reference", "@b")], "ValidationError", id="reference-repeated"),
            pytest.param([("reference", "@a"), ("type", "llm"), ("type", "extract")], "ValidationError", id="type-repeated"),
            pytest.param([("reference", "")], "InvalidModelReference", id="empty"),
            pytest.param([("reference", "   ")], "InvalidModelReference", id="blank"),
            pytest.param([("reference", "~")], "InvalidModelReference", id="sigil-alone"),
            pytest.param([("reference", "handle:")], "InvalidModelReference", id="namespace-alone"),
            pytest.param([("reference", "@" + "x" * MAX_MODEL_REFERENCE_LENGTH)], "InvalidModelReference", id="past-the-bound"),
            pytest.param([("reference", "@a"), ("type", "bogus_category")], "InvalidModelCategory", id="type-unknown"),
            pytest.param([("reference", "@a"), ("type", "")], "InvalidModelCategory", id="type-empty"),
        ],
    )
    def test_a_request_with_no_verdict_is_an_input_422(self, params: list[tuple[str, str]], error_type: str):
        client = _build_client()

        response = client.get(_CHECK_PATH, params=tuple(params))

        assert response.status_code == 422, response.text
        assert response.headers["content-type"] == "application/problem+json"
        problem = response.json()
        assert problem["error_type"] == error_type
        assert problem["error_domain"] == "input"
        assert "resolution" not in problem
