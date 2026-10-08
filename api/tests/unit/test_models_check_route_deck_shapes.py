"""The model reference check route, `GET /v1/models/check`, on hand-built decks whose bindings lead back to themselves or share names."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.llm.llm_setting import LLMSetting, LLMSettingChoicesDefaults
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_spec_index import ModelSpecIndex
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.models.model_deck_config import ModelDeckConfig
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.system.runtime import ProblemReaction
from pytest_mock import MockerFixture

from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router

_CHECK_PATH = "/v1/models/check"
_GET_MODEL_DECK_TARGET = "pipelex_api.routes.pipelex.agent.models.get_model_deck"


def _model_spec(name: str, model_type: ModelType) -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name="test_backend",
        name=name,
        sdk="test_sdk",
        model_type=model_type,
        model_id=f"test_model_{name}",
        costs={CostCategory.INPUT: 0.001, CostCategory.OUTPUT: 0.002},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=1000,
        max_prompt_images=None,
    )


def _make_deck() -> ModelDeck:
    """A deck where an alias and a waterfall lead to each other, an image-generation waterfall is named like an LLM
    and lists its own name first, and an alias and a waterfall share a name.
    """
    return ModelDeck(
        inference_models=ModelSpecIndex.make_from_specs(
            model_specs=[
                _model_spec("gpt-4o-mini", ModelType.LLM),
                _model_spec("claude-x", ModelType.LLM),
            ]
        ),
        llm_default_temperature=0.7,
        llm_aliases={"cycle-a": "~cycle-waterfall", "best-gpt": "gpt-4o-mini"},
        llm_waterfalls={"cycle-waterfall": ["@cycle-a"], "best-gpt": ["claude-x"]},
        llm_choice_defaults=LLMSettingChoicesDefaults(
            default_temperature=0.7,
            for_text=LLMSetting(model="gpt-4o-mini", temperature=0.7),
            for_object=LLMSetting(model="gpt-4o-mini", temperature=0.1),
        ),
        extract_choice_default="extract-engine",
        img_gen_default_quality=Quality.MEDIUM,
        img_gen_waterfalls={"gpt-4o-mini": ["gpt-4o-mini", "img-unserved"]},
        img_gen_choice_default="img-unserved",
        search_choice_default="@default-search",
        model_deck_config=ModelDeckConfig(is_model_fallback_enabled=True, missing_presets_reaction=ProblemReaction.NONE),
    )


def _verdict(mocker: MockerFixture, *, reference: str, category: str) -> dict[str, Any]:
    mocker.patch(_GET_MODEL_DECK_TARGET, return_value=_make_deck())
    app = FastAPI()
    app.include_router(api_router, prefix="/v1")
    register_exception_handlers(app)
    response = TestClient(app).get(_CHECK_PATH, params={"reference": reference, "type": category})
    assert response.status_code == 200, response.text
    verdict: dict[str, Any] = response.json()
    return verdict


class TestModelsCheckRouteDeckShapes:
    @pytest.mark.parametrize(
        ("reference", "category", "expected_match"),
        [
            pytest.param("@cycle-a", "llm", {"category": "llm", "resolves_to": None, "target": "~cycle-waterfall"}, id="alias-into-waterfall"),
            pytest.param("~cycle-waterfall", "llm", {"category": "llm", "resolves_to": None, "fallbacks": ["@cycle-a"]}, id="waterfall-into-alias"),
            pytest.param("gpt-4o-mini", "img_gen", {"category": "img_gen", "resolves_to": None, "via": ["~gpt-4o-mini"]}, id="waterfall-into-itself"),
        ],
    )
    def test_a_binding_leading_back_to_itself_is_resolved_to_no_model(
        self,
        mocker: MockerFixture,
        reference: str,
        category: str,
        expected_match: dict[str, Any],
    ):
        verdict = _verdict(mocker, reference=reference, category=category)

        assert verdict["resolution"] == "resolved"
        assert verdict["matches"] == [expected_match]

    @pytest.mark.parametrize(
        ("reference", "expected_model"),
        [
            pytest.param("~best-gpt", "claude-x", id="waterfall"),
            pytest.param("@best-gpt", "gpt-4o-mini", id="alias"),
            pytest.param("best-gpt", "gpt-4o-mini", id="bare-name"),
        ],
    )
    def test_an_alias_and_a_waterfall_sharing_a_name_each_resolve_by_their_sigil(self, mocker: MockerFixture, reference: str, expected_model: str):
        verdict = _verdict(mocker, reference=reference, category="llm")

        (match,) = verdict["matches"]
        assert match["resolves_to"] == expected_model
