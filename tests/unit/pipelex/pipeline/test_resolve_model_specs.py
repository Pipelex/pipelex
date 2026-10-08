"""`resolve_model_specs`, the models a file-input consumer's reference can be served by, reads a bare name as the run does."""

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.config_cogt import ModelDeckConfig
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.llm.llm_setting import LLMSetting, LLMSettingChoicesDefaults
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.pipeline.file_input_consumers import resolve_model_specs
from pipelex.system.runtime import ProblemReaction

_GET_MODEL_DECK_TARGET = "pipelex.pipeline.file_input_consumers.get_model_deck"


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
    """A deck where an LLM's name is also an extraction alias and an image-generation waterfall."""
    return ModelDeck(
        inference_models={
            "gpt-4o-mini": _model_spec("gpt-4o-mini", ModelType.LLM),
            "extract-engine": _model_spec("extract-engine", ModelType.TEXT_EXTRACTOR),
            "img-painter": _model_spec("img-painter", ModelType.IMG_GEN),
        },
        llm_default_temperature=0.7,
        llm_choice_defaults=LLMSettingChoicesDefaults(
            default_temperature=0.7,
            for_text=LLMSetting(model="gpt-4o-mini", temperature=0.7),
            for_object=LLMSetting(model="gpt-4o-mini", temperature=0.1),
        ),
        extract_aliases={"gpt-4o-mini": "extract-engine"},
        extract_choice_default="extract-engine",
        img_gen_default_quality=Quality.MEDIUM,
        img_gen_waterfalls={"gpt-4o-mini": ["gpt-4o-mini", "img-painter"]},
        img_gen_choice_default="img-painter",
        search_choice_default="@default-search",
        model_deck_config=ModelDeckConfig(is_model_fallback_enabled=True, missing_presets_reaction=ProblemReaction.NONE),
    )


class TestResolveModelSpecs:
    @pytest.mark.parametrize(
        ("model_type", "expected_names"),
        [
            pytest.param(ModelType.LLM, ["gpt-4o-mini"], id="the-model-of-its-type"),
            pytest.param(ModelType.TEXT_EXTRACTOR, ["extract-engine"], id="an-alias-of-that-name"),
            pytest.param(ModelType.IMG_GEN, ["img-painter"], id="a-waterfall-of-that-name"),
            pytest.param(ModelType.SEARCH, [], id="nothing-of-that-name"),
        ],
    )
    def test_a_model_served_as_another_type_gives_way_to_an_alias_or_a_waterfall_of_its_name(
        self,
        mocker: MockerFixture,
        model_type: ModelType,
        expected_names: list[str],
    ) -> None:
        model_deck = _make_deck()
        mocker.patch(_GET_MODEL_DECK_TARGET, return_value=model_deck)

        model_specs = resolve_model_specs(model_reference="gpt-4o-mini", model_type=model_type)

        assert [model_spec.name for model_spec in model_specs] == expected_names
        run_model = model_deck.peek_inference_model(model_handle="gpt-4o-mini", model_type=model_type)
        assert (run_model.name if run_model else None) == (expected_names[0] if expected_names else None)
