"""The deck's own bindings and refusals hold a bare handle to the model type it is named for."""

import pytest
from pytest_mock import MockerFixture

from pipelex import log
from pipelex.cogt.config_cogt import ModelDeckConfig
from pipelex.cogt.exceptions import ImgGenHandleNotFoundError, LLMHandleNotFoundError, ModelChoiceNotFoundError, ModelDeckPresetValidatonError
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.img_gen.img_gen_setting import ImgGenSetting
from pipelex.cogt.llm.llm_setting import LLMSetting, LLMSettingChoicesDefaults
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_spec_index import ModelSpecIndex
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.system.runtime import ProblemReaction


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


def _make_deck(
    *,
    llm_presets: dict[str, LLMSetting] | None = None,
    img_gen_presets: dict[str, ImgGenSetting] | None = None,
    missing_presets_reaction: ProblemReaction = ProblemReaction.NONE,
) -> ModelDeck:
    """A deck serving LLMs and an image-generation model."""
    return ModelDeck(
        inference_models=ModelSpecIndex.make_from_specs(
            model_specs=[
                _model_spec("gpt-4o-mini", ModelType.LLM),
                _model_spec("claude-x", ModelType.LLM),
                _model_spec("img-painter", ModelType.IMG_GEN),
            ]
        ),
        llm_default_temperature=0.7,
        llm_presets=llm_presets or {},
        llm_choice_defaults=LLMSettingChoicesDefaults(
            default_temperature=0.7,
            for_text=LLMSetting(model="gpt-4o-mini", temperature=0.7),
            for_object=LLMSetting(model="gpt-4o-mini", temperature=0.1),
        ),
        extract_choice_default="extract-engine",
        img_gen_default_quality=Quality.MEDIUM,
        img_gen_presets=img_gen_presets or {},
        img_gen_choice_default="img-painter",
        search_choice_default="@default-search",
        model_deck_config=ModelDeckConfig(is_model_fallback_enabled=True, missing_presets_reaction=missing_presets_reaction),
    )


def _build_setting(*, model_deck: ModelDeck, model_type: ModelType, model_choice: str) -> None:
    """Build the setting a pipe of this type naming `model_choice` runs with."""
    match model_type:
        case ModelType.LLM:
            model_deck.get_llm_setting(llm_choice=model_choice)
        case ModelType.TEXT_EXTRACTOR:
            model_deck.get_extract_setting(extract_choice=model_choice)
        case ModelType.IMG_GEN:
            model_deck.get_img_gen_setting(img_gen_choice=model_choice)
        case ModelType.SEARCH:
            model_deck.get_search_setting(search_choice=model_choice)
        case ModelType.DOC_GEN:
            model_deck.get_doc_gen_setting(doc_gen_choice=model_choice)
        case ModelType.JUDGMENT:
            model_deck.get_judgment_setting(judgment_choice=model_choice)


class TestModelDeckTypeStrictness:
    def test_an_llm_preset_naming_an_image_generation_model_refuses_boot_naming_the_type_needed(self) -> None:
        model_deck = _make_deck(llm_presets={"painter": LLMSetting(model="img-painter", temperature=0.5)})

        with pytest.raises(LLMHandleNotFoundError) as exc_info:
            model_deck.validate_llm_presets()

        assert str(exc_info.value) == "LLM preset 'painter': Model handle 'img-painter' is served by the model deck, but not as an LLM"
        assert exc_info.value.preset_id == "painter"
        assert exc_info.value.model_handle == "img-painter"

    def test_an_image_generation_preset_naming_an_llm_refuses_boot_naming_the_type_needed(self) -> None:
        model_deck = _make_deck(img_gen_presets={"writer": ImgGenSetting(model="claude-x")})

        with pytest.raises(ImgGenHandleNotFoundError) as exc_info:
            model_deck.validate_img_gen_presets()

        assert str(exc_info.value) == (
            "Image generation preset 'writer': Model handle 'claude-x' is served by the model deck, but not as an image-generation model"
        )

    def test_a_preset_naming_a_model_served_nowhere_says_it_was_not_found(self) -> None:
        model_deck = _make_deck(llm_presets={"ghost": LLMSetting(model="gpt-9", temperature=0.5)})

        with pytest.raises(LLMHandleNotFoundError) as exc_info:
            model_deck.validate_llm_presets()

        assert str(exc_info.value) == "LLM preset 'ghost': Model handle 'gpt-9' was not found in the model deck"

    def test_a_preset_naming_an_unknown_alias_says_the_reference_was_not_found(self) -> None:
        model_deck = _make_deck(llm_presets={"ghost": LLMSetting(model="@nowhere", temperature=0.5)})

        with pytest.raises(LLMHandleNotFoundError) as exc_info:
            model_deck.validate_llm_presets()

        assert str(exc_info.value) == "LLM preset 'ghost': Model reference '@nowhere' was not found in the model deck"

    def test_the_boot_refusal_carries_the_preset_sentence(self) -> None:
        model_deck = _make_deck(
            llm_presets={"painter": LLMSetting(model="img-painter", temperature=0.5)},
            missing_presets_reaction=ProblemReaction.RAISE,
        )

        with pytest.raises(ModelDeckPresetValidatonError, match=r"Failed to validate all LLM presets: LLM preset 'painter': .* but not as an LLM"):
            model_deck.validate_registered_models()

    def test_a_deck_that_logs_its_unresolvable_presets_warns_once_per_model_type_with_the_same_fields(self, mocker: MockerFixture) -> None:
        """Each model type's refusal is logged through one helper, so every one of them names its type, preset and model alike."""
        model_deck = _make_deck(
            llm_presets={"painter": LLMSetting(model="img-painter", temperature=0.5)},
            img_gen_presets={"writer": ImgGenSetting(model="claude-x")},
            missing_presets_reaction=ProblemReaction.LOG,
        )
        warning_spy = mocker.patch.object(log, "warning")

        model_deck.validate_registered_models()

        assert [call.args for call in warning_spy.call_args_list] == [("A preset of the model deck names a model the deck cannot resolve",)] * 2
        llm_fields, img_gen_fields = [call.kwargs["fields"] for call in warning_spy.call_args_list]
        assert llm_fields == {
            "model_type": ModelType.LLM,
            "preset_id": "painter",
            "model_handle": "img-painter",
            "error.type": "LLMHandleNotFoundError",
            "error.message": "LLM preset 'painter': Model handle 'img-painter' is served by the model deck, but not as an LLM",
        }
        assert img_gen_fields == {
            "model_type": ModelType.IMG_GEN,
            "preset_id": "writer",
            "model_handle": "claude-x",
            "error.type": "ImgGenHandleNotFoundError",
            "error.message": (
                "Image generation preset 'writer': Model handle 'claude-x' is served by the model deck, but not as an image-generation model"
            ),
        }

    def test_an_llm_override_naming_an_image_generation_model_is_refused_with_the_llms_alone(self) -> None:
        model_deck = _make_deck()

        with pytest.raises(ModelChoiceNotFoundError) as exc_info:
            model_deck.check_llm_choice(llm_choice="img-painter")

        assert exc_info.value.message.startswith("Model handle 'img-painter' is served by the model deck, but not as an LLM\n")
        assert "Available handle: claude-x, gpt-4o-mini" in exc_info.value.message
        assert exc_info.value.available_options == ["claude-x", "gpt-4o-mini"]

    @pytest.mark.parametrize(
        ("model_type", "expected_options"),
        [
            (ModelType.LLM, ["claude-x", "gpt-4o-mini"]),
            (ModelType.IMG_GEN, ["img-painter"]),
            (ModelType.SEARCH, []),
        ],
    )
    def test_a_handle_refusal_offers_the_models_of_its_type_alone(self, model_type: ModelType, expected_options: list[str]) -> None:
        model_deck = _make_deck()

        with pytest.raises(ModelChoiceNotFoundError) as exc_info:
            _build_setting(model_deck=model_deck, model_type=model_type, model_choice="held-nowhere")

        assert exc_info.value.available_options == expected_options
        assert model_deck.inference_models.handles_of_type(model_type=model_type) == expected_options
