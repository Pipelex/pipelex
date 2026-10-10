from pytest_mock import MockerFixture

from pipelex.cogt.config_cogt import ModelDeckConfig
from pipelex.cogt.extract.extract_setting import ExtractSetting
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.llm.llm_setting import LLMSetting, LLMSettingChoicesDefaults
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_spec_index import ModelSpecIndex
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.models.model_reference import ModelReferenceKind
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.system.runtime import ProblemReaction


def _make_deck() -> ModelDeck:
    """A deck serving one LLM, where `twin` is at once a model, an alias and a preset."""
    twin_model = InferenceModelSpec(
        backend_name="test_backend",
        name="twin",
        sdk="test_sdk",
        model_type=ModelType.LLM,
        model_id="test_model_twin",
        costs={CostCategory.INPUT: 0.001, CostCategory.OUTPUT: 0.002},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=1000,
        max_prompt_images=None,
    )
    return ModelDeck(
        inference_models=ModelSpecIndex.make_from_specs(model_specs=[twin_model]),
        llm_default_temperature=0.7,
        llm_aliases={"twin": "twin"},
        llm_waterfalls={},
        llm_presets={"twin": LLMSetting(model="twin", temperature=0.3)},
        llm_choice_defaults=LLMSettingChoicesDefaults(
            default_temperature=0.7,
            for_text=LLMSetting(model="twin", temperature=0.7),
            for_object=LLMSetting(model="twin", temperature=0.7),
        ),
        extract_aliases={},
        extract_waterfalls={},
        extract_presets={"deck-extract-preset": ExtractSetting(model="deck-extract-preset-model")},
        extract_choice_default="$deck-extract-preset",
        img_gen_default_quality=Quality.MEDIUM,
        img_gen_aliases={},
        img_gen_waterfalls={},
        img_gen_presets={},
        img_gen_choice_default="deck-img-gen-default",
        search_aliases={},
        search_waterfalls={},
        search_presets={},
        search_choice_default="deck-search-default",
        model_deck_config=ModelDeckConfig(is_model_fallback_enabled=True, missing_presets_reaction=ProblemReaction.NONE),
    )


class TestModelDeckAmbiguousBareHandle:
    def test_the_warning_names_the_handle_its_type_and_every_kind_it_also_names(self, mocker: MockerFixture) -> None:
        """The kinds ride as a field, so one fixed message groups every such warning whatever the name."""
        deck = _make_deck()
        warning = mocker.patch("pipelex.cogt.models.model_deck.log.warning")

        setting = deck.get_llm_setting(llm_choice="twin")

        assert setting.model == "twin"
        warning.assert_called_once()
        assert warning.call_args.kwargs["fields"] == {
            "model_handle": "twin",
            "model_type": ModelType.LLM,
            "matching_reference_kinds": [ModelReferenceKind.PRESET, ModelReferenceKind.ALIAS],
        }

    def test_a_bare_name_that_names_nothing_else_is_not_warned_about(self, mocker: MockerFixture) -> None:
        deck = _make_deck()
        deck.llm_aliases.clear()
        deck.llm_presets.clear()
        warning = mocker.patch("pipelex.cogt.models.model_deck.log.warning")

        deck.get_llm_setting(llm_choice="twin")

        warning.assert_not_called()
