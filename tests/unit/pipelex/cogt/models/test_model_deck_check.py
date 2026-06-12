from typing import Any, Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.config_cogt import ModelDeckConfig
from pipelex.cogt.exceptions import ModelChoiceNotFoundError
from pipelex.cogt.extract.extract_setting import ExtractSetting
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.img_gen.img_gen_setting import ImgGenSetting
from pipelex.cogt.llm.llm_setting import LLMSetting, LLMSettingChoicesDefaults
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.models.model_deck_check import (
    check_extract_choice_with_deck,
    check_img_gen_choice_with_deck,
    check_llm_choice_with_deck,
    check_search_choice_with_deck,
)
from pipelex.cogt.models.model_reference import ModelReference, ModelReferenceKind
from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.system.runtime import ProblemReaction

CheckFunction = Callable[[Any], None]

GET_MODEL_DECK_TARGET = "pipelex.cogt.models.model_deck_check.get_model_deck"


class TestModelDeckCheck:
    def _create_model_spec(self, name: str, model_type: ModelType) -> InferenceModelSpec:
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

    def _create_test_model_deck(self) -> ModelDeck:
        """Build a deck with one preset, alias, waterfall and handle per model type."""
        return ModelDeck(
            inference_models={
                "gpt-4o-mini": self._create_model_spec("gpt-4o-mini", ModelType.LLM),
                "extract-engine": self._create_model_spec("extract-engine", ModelType.TEXT_EXTRACTOR),
                "img-painter": self._create_model_spec("img-painter", ModelType.IMG_GEN),
                "web-searcher": self._create_model_spec("web-searcher", ModelType.SEARCH),
            },
            # LLM-specific
            llm_default_temperature=0.7,
            llm_aliases={"best-gpt": "gpt-4o-mini"},
            llm_waterfalls={"small-llm": ["gpt-4o-mini"]},
            llm_presets={"cheap-llm": LLMSetting(model="gpt-4o-mini", temperature=0.5)},
            llm_choice_defaults=LLMSettingChoicesDefaults(
                default_temperature=0.7,
                for_text=LLMSetting(model="default_text", temperature=0.7, max_tokens=1000),
                for_object=LLMSetting(model="default_object", temperature=0.1, max_tokens=1000),
            ),
            # Extract-specific
            extract_aliases={"best-extract": "extract-engine"},
            extract_waterfalls={"fallback-extract": ["extract-engine"]},
            extract_presets={"cheap-extract": ExtractSetting(model="extract-engine")},
            extract_choice_default="default-extract-document",
            # ImgGen-specific
            img_gen_default_quality=Quality.MEDIUM,
            img_gen_aliases={"best-img": "img-painter"},
            img_gen_waterfalls={"fallback-img": ["img-painter"]},
            img_gen_presets={"cheap-img": ImgGenSetting(model="img-painter")},
            img_gen_choice_default="gen_image_basic",
            # Search-specific
            search_aliases={"best-search": "web-searcher"},
            search_waterfalls={"fallback-search": ["web-searcher"]},
            search_presets={"cheap-search": SearchSetting(model="web-searcher")},
            search_choice_default="@default-search",
            model_deck_config=ModelDeckConfig(is_model_fallback_enabled=False, missing_presets_reaction=ProblemReaction.NONE),
        )

    @pytest.mark.parametrize(
        ("check_fn", "setting_instance"),
        [
            pytest.param(check_llm_choice_with_deck, LLMSetting(model="gpt-4o-mini", temperature=0.5), id="llm"),
            pytest.param(check_extract_choice_with_deck, ExtractSetting(model="extract-engine"), id="extract"),
            pytest.param(check_search_choice_with_deck, SearchSetting(model="web-searcher"), id="search"),
            pytest.param(check_img_gen_choice_with_deck, ImgGenSetting(model="img-painter"), id="img_gen"),
        ],
    )
    def test_setting_instance_short_circuits_without_deck_lookup(
        self,
        mocker: MockerFixture,
        check_fn: CheckFunction,
        setting_instance: Any,
    ) -> None:
        """A concrete Setting instance is accepted as-is without ever consulting the deck."""
        get_deck_mock = mocker.patch(GET_MODEL_DECK_TARGET)

        check_fn(setting_instance)

        get_deck_mock.assert_not_called()

    @pytest.mark.parametrize(
        ("check_fn", "model_choice"),
        [
            pytest.param(check_llm_choice_with_deck, "$cheap-llm", id="llm-preset"),
            pytest.param(check_llm_choice_with_deck, "@best-gpt", id="llm-alias"),
            pytest.param(check_llm_choice_with_deck, "~small-llm", id="llm-waterfall"),
            pytest.param(check_llm_choice_with_deck, "gpt-4o-mini", id="llm-handle"),
            pytest.param(check_extract_choice_with_deck, "$cheap-extract", id="extract-preset"),
            pytest.param(check_extract_choice_with_deck, "@best-extract", id="extract-alias"),
            pytest.param(check_extract_choice_with_deck, "~fallback-extract", id="extract-waterfall"),
            pytest.param(check_extract_choice_with_deck, "extract-engine", id="extract-handle"),
            pytest.param(check_search_choice_with_deck, "$cheap-search", id="search-preset"),
            pytest.param(check_search_choice_with_deck, "@best-search", id="search-alias"),
            pytest.param(check_search_choice_with_deck, "~fallback-search", id="search-waterfall"),
            pytest.param(check_search_choice_with_deck, "web-searcher", id="search-handle"),
            pytest.param(check_img_gen_choice_with_deck, "$cheap-img", id="img_gen-preset"),
            pytest.param(check_img_gen_choice_with_deck, "@best-img", id="img_gen-alias"),
            pytest.param(check_img_gen_choice_with_deck, "~fallback-img", id="img_gen-waterfall"),
            pytest.param(check_img_gen_choice_with_deck, "img-painter", id="img_gen-handle"),
        ],
    )
    def test_found_choice_returns_none(
        self,
        mocker: MockerFixture,
        check_fn: CheckFunction,
        model_choice: str,
    ) -> None:
        """Each reference kind resolves successfully (no exception) when the name exists in the right deck collection."""
        model_deck = self._create_test_model_deck()
        mocker.patch(GET_MODEL_DECK_TARGET, return_value=model_deck)

        check_fn(model_choice)

    @pytest.mark.parametrize(
        ("check_fn", "model_choice", "expected_kind", "expected_model_type", "options_attr"),
        [
            pytest.param(check_llm_choice_with_deck, "$missing-preset", ModelReferenceKind.PRESET, ModelType.LLM, "llm_presets", id="llm-preset"),
            pytest.param(check_llm_choice_with_deck, "@missing-alias", ModelReferenceKind.ALIAS, ModelType.LLM, "llm_aliases", id="llm-alias"),
            pytest.param(
                check_llm_choice_with_deck, "~missing-waterfall", ModelReferenceKind.WATERFALL, ModelType.LLM, "llm_waterfalls", id="llm-waterfall"
            ),
            pytest.param(check_llm_choice_with_deck, "missing-handle", ModelReferenceKind.HANDLE, ModelType.LLM, "inference_models", id="llm-handle"),
            pytest.param(
                check_extract_choice_with_deck,
                "$missing-preset",
                ModelReferenceKind.PRESET,
                ModelType.TEXT_EXTRACTOR,
                "extract_presets",
                id="extract-preset",
            ),
            pytest.param(
                check_extract_choice_with_deck,
                "@missing-alias",
                ModelReferenceKind.ALIAS,
                ModelType.TEXT_EXTRACTOR,
                "extract_aliases",
                id="extract-alias",
            ),
            pytest.param(
                check_extract_choice_with_deck,
                "~missing-waterfall",
                ModelReferenceKind.WATERFALL,
                ModelType.TEXT_EXTRACTOR,
                "extract_waterfalls",
                id="extract-waterfall",
            ),
            pytest.param(
                check_extract_choice_with_deck,
                "missing-handle",
                ModelReferenceKind.HANDLE,
                ModelType.TEXT_EXTRACTOR,
                "inference_models",
                id="extract-handle",
            ),
            pytest.param(
                check_search_choice_with_deck,
                "$missing-preset",
                ModelReferenceKind.PRESET,
                ModelType.SEARCH,
                "search_presets",
                id="search-preset",
            ),
            pytest.param(
                check_search_choice_with_deck, "@missing-alias", ModelReferenceKind.ALIAS, ModelType.SEARCH, "search_aliases", id="search-alias"
            ),
            pytest.param(
                check_search_choice_with_deck,
                "~missing-waterfall",
                ModelReferenceKind.WATERFALL,
                ModelType.SEARCH,
                "search_waterfalls",
                id="search-waterfall",
            ),
            pytest.param(
                check_search_choice_with_deck,
                "missing-handle",
                ModelReferenceKind.HANDLE,
                ModelType.SEARCH,
                "inference_models",
                id="search-handle",
            ),
            pytest.param(
                check_img_gen_choice_with_deck,
                "$missing-preset",
                ModelReferenceKind.PRESET,
                ModelType.IMG_GEN,
                "img_gen_presets",
                id="img_gen-preset",
            ),
            pytest.param(
                check_img_gen_choice_with_deck, "@missing-alias", ModelReferenceKind.ALIAS, ModelType.IMG_GEN, "img_gen_aliases", id="img_gen-alias"
            ),
            pytest.param(
                check_img_gen_choice_with_deck,
                "~missing-waterfall",
                ModelReferenceKind.WATERFALL,
                ModelType.IMG_GEN,
                "img_gen_waterfalls",
                id="img_gen-waterfall",
            ),
            pytest.param(
                check_img_gen_choice_with_deck,
                "missing-handle",
                ModelReferenceKind.HANDLE,
                ModelType.IMG_GEN,
                "inference_models",
                id="img_gen-handle",
            ),
        ],
    )
    def test_not_found_choice_raises_with_context(
        self,
        mocker: MockerFixture,
        check_fn: CheckFunction,
        model_choice: str,
        expected_kind: ModelReferenceKind,
        expected_model_type: ModelType,
        options_attr: str,
    ) -> None:
        """A missing name raises ModelChoiceNotFoundError carrying the sigil-form choice, kind, type and the right deck collection."""
        model_deck = self._create_test_model_deck()
        mocker.patch(GET_MODEL_DECK_TARGET, return_value=model_deck)

        with pytest.raises(ModelChoiceNotFoundError) as exc_info:
            check_fn(model_choice)

        error = exc_info.value
        assert error.model_choice == model_choice
        assert error.reference_kind == expected_kind
        assert error.model_type == expected_model_type
        expected_options: dict[str, Any] = getattr(model_deck, options_attr)
        assert error.available_options == list(expected_options.keys())

    def test_near_miss_handle_yields_fuzzy_suggestion(self, mocker: MockerFixture) -> None:
        """A typo'd handle gets a fuzzy suggestion pointing at the close-by real handle."""
        model_deck = self._create_test_model_deck()
        mocker.patch(GET_MODEL_DECK_TARGET, return_value=model_deck)

        with pytest.raises(ModelChoiceNotFoundError) as exc_info:
            check_llm_choice_with_deck("gpt-4o-mimi")

        error = exc_info.value
        assert "gpt-4o-mini" in error.suggestions
        assert "gpt-4o-mini" in str(error)

    def test_alias_referenced_with_preset_sigil_yields_wrong_sigil_hint(self, mocker: MockerFixture) -> None:
        """A name that exists as an alias but is referenced with the preset sigil gets a wrong-sigil hint."""
        model_deck = self._create_test_model_deck()
        mocker.patch(GET_MODEL_DECK_TARGET, return_value=model_deck)

        with pytest.raises(ModelChoiceNotFoundError) as exc_info:
            check_llm_choice_with_deck("$best-gpt")

        error = exc_info.value
        assert error.wrong_sigil_hints
        assert "best-gpt exists as @best-gpt (alias)" in error.wrong_sigil_hints

    @pytest.mark.parametrize(
        "model_choice",
        [
            pytest.param("$cheap-llm", id="preset"),
            pytest.param("@best-gpt", id="alias"),
            pytest.param("~small-llm", id="waterfall"),
            pytest.param("gpt-4o-mini", id="handle"),
        ],
    )
    def test_string_and_model_reference_inputs_are_equivalent(self, mocker: MockerFixture, model_choice: str) -> None:
        """Raw strings and pre-parsed ModelReference objects are both accepted (no exception) for every kind."""
        model_deck = self._create_test_model_deck()
        mocker.patch(GET_MODEL_DECK_TARGET, return_value=model_deck)

        check_llm_choice_with_deck(model_choice)
        check_llm_choice_with_deck(ModelReference.parse(model_choice))
