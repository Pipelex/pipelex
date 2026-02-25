import pytest

from pipelex.cogt.config_cogt import ModelDeckConfig
from pipelex.cogt.exceptions import ModelChoiceNotFoundError, ModelWaterfallError
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.llm.llm_setting import LLMSetting, LLMSettingChoicesDefaults
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.system.runtime import ProblemReaction


class TestModelDeckGetOptionalInferenceModel:
    def _create_test_model_spec(self, name: str) -> InferenceModelSpec:
        return InferenceModelSpec(
            backend_name="test_backend",
            name=name,
            sdk="test_sdk",
            model_type=ModelType.LLM,
            model_id=f"test_model_{name}",
            costs={CostCategory.INPUT: 0.001, CostCategory.OUTPUT: 0.002},
            thinking_mode=ThinkingMode.NONE,
            max_tokens=1000,
            max_prompt_images=None,
        )

    def _create_test_model_deck(
        self,
        inference_models: dict[str, InferenceModelSpec] | None = None,
        llm_aliases: dict[str, str] | None = None,
        llm_waterfalls: dict[str, list[str]] | None = None,
        is_model_fallback_enabled: bool = False,
    ) -> ModelDeck:
        return ModelDeck(
            inference_models=inference_models or {},
            # LLM-specific
            llm_default_temperature=0.7,
            llm_aliases=llm_aliases or {},
            llm_waterfalls=llm_waterfalls or {},
            llm_presets={},
            llm_choice_defaults=LLMSettingChoicesDefaults(
                default_temperature=0.7,
                for_text=LLMSetting(model="default_text", temperature=0.7, max_tokens=1000),
                for_object=LLMSetting(model="default_object", temperature=0.1, max_tokens=1000),
            ),
            # Extract-specific
            extract_aliases={},
            extract_waterfalls={},
            extract_presets={},
            extract_choice_default="default-extract-document",
            # ImgGen-specific
            img_gen_default_quality=Quality.MEDIUM,
            img_gen_aliases={},
            img_gen_waterfalls={},
            img_gen_presets={},
            img_gen_choice_default="gen_image_basic",
            model_deck_config=ModelDeckConfig(is_model_fallback_enabled=is_model_fallback_enabled, missing_presets_reaction=ProblemReaction.NONE),
        )

    def test_direct_model_lookup_success(self):
        # Arrange
        model_spec = self._create_test_model_spec("gpt-4")
        model_deck = self._create_test_model_deck(inference_models={"gpt-4": model_spec})

        # Act
        result = model_deck.get_optional_inference_model("gpt-4", model_type=ModelType.LLM)

        # Assert
        assert result == model_spec

    def test_direct_model_lookup_not_found(self):
        # Arrange
        model_deck = self._create_test_model_deck()

        # Act
        result = model_deck.get_optional_inference_model("nonexistent-model", model_type=ModelType.LLM)

        # Assert
        assert result is None

    def test_simple_string_alias_resolution_success(self):
        # Arrange
        model_spec = self._create_test_model_spec("gpt-4")
        model_deck = self._create_test_model_deck(inference_models={"gpt-4": model_spec}, llm_aliases={"best-gpt": "gpt-4"})

        # Act
        result = model_deck.get_optional_inference_model("best-gpt", model_type=ModelType.LLM)

        # Assert
        assert result == model_spec

    def test_simple_string_alias_resolution_not_found(self):
        # Arrange
        model_deck = self._create_test_model_deck(llm_aliases={"best-gpt": "nonexistent-model"})

        # Act
        result = model_deck.get_optional_inference_model("best-gpt", model_type=ModelType.LLM)

        # Assert
        assert result is None

    def test_list_alias_resolution_first_success(self):
        # Arrange
        model_spec = self._create_test_model_spec("gpt-4")
        model_deck = self._create_test_model_deck(
            inference_models={"gpt-4": model_spec},
            llm_waterfalls={"dummy-model-handle": ["gpt-4", "claude-3"]},
            is_model_fallback_enabled=True,
        )

        # Act
        result = model_deck.get_optional_inference_model("dummy-model-handle", model_type=ModelType.LLM)

        # Assert
        assert result == model_spec

    def test_list_alias_resolution_second_success(self):
        # Arrange
        model_spec = self._create_test_model_spec("claude-3")
        model_deck = self._create_test_model_deck(
            inference_models={"claude-3": model_spec},
            llm_waterfalls={"dummy-model-handle": ["nonexistent-model", "claude-3"]},
            is_model_fallback_enabled=True,
        )

        # Act
        result = model_deck.get_optional_inference_model("dummy-model-handle", model_type=ModelType.LLM)

        # Assert
        assert result == model_spec

    def test_list_alias_resolution_none_found(self):
        # Arrange
        model_deck = self._create_test_model_deck(
            llm_waterfalls={"dummy-model-handle": ["nonexistent-1", "nonexistent-2"]},
            is_model_fallback_enabled=True,
        )

        # Act & Assert
        with pytest.raises(
            ModelWaterfallError,
            match=r"is a waterfall.*but none of the fallback models were found",
        ):
            model_deck.get_optional_inference_model("dummy-model-handle", model_type=ModelType.LLM)

    def test_recursive_alias_resolution_success(self):
        # Arrange
        model_spec = self._create_test_model_spec("gpt-4")
        model_deck = self._create_test_model_deck(
            inference_models={"gpt-4": model_spec}, llm_aliases={"dummy-model-handle": "best-gpt", "best-gpt": "gpt-4"}
        )

        # Act
        result = model_deck.get_optional_inference_model("dummy-model-handle", model_type=ModelType.LLM)

        # Assert
        assert result == model_spec

    def test_recursive_alias_resolution_with_list(self):
        # Arrange
        model_spec = self._create_test_model_spec("gpt-4")
        model_deck = self._create_test_model_deck(
            inference_models={"gpt-4": model_spec},
            llm_aliases={"best-gpt": "gpt-4"},
            llm_waterfalls={"dummy-model-handle": ["nonexistent", "best-gpt"]},
            is_model_fallback_enabled=True,
        )

        # Act
        result = model_deck.get_optional_inference_model("dummy-model-handle", model_type=ModelType.LLM)

        # Assert
        assert result == model_spec

    def test_empty_alias_list(self):
        # Arrange
        model_deck = self._create_test_model_deck(
            llm_waterfalls={"empty-alias": []},
            is_model_fallback_enabled=True,
        )

        # Act
        result = model_deck.get_optional_inference_model("empty-alias", model_type=ModelType.LLM)

        # Assert
        assert result is None

    def test_circular_alias_prevention(self):
        """Test that circular alias references are detected and handled gracefully."""
        # Arrange
        model_deck = self._create_test_model_deck(llm_aliases={"alias-a": "alias-b", "alias-b": "alias-a"})

        # Act
        result = model_deck.get_optional_inference_model("alias-a", model_type=ModelType.LLM)

        # Assert - cycle detection returns None instead of causing RecursionError
        assert result is None

    def test_model_type_mismatch_returns_none(self):
        """Test that requesting a model with wrong model_type returns None."""
        # Arrange - create a TEXT_EXTRACTOR model
        extractor_spec = InferenceModelSpec(
            backend_name="test_backend",
            name="mistral-extractor",
            sdk="test_sdk",
            model_type=ModelType.TEXT_EXTRACTOR,
            model_id="mistral-extractor-id",
            costs={CostCategory.INPUT: 0.001, CostCategory.OUTPUT: 0.002},
            thinking_mode=ThinkingMode.NONE,
            max_tokens=1000,
            max_prompt_images=None,
        )
        model_deck = self._create_test_model_deck(inference_models={"mistral-extractor": extractor_spec})

        # Act - request it as LLM
        result = model_deck.get_optional_inference_model("mistral-extractor", model_type=ModelType.LLM)

        # Assert - should return None due to model_type mismatch
        assert result is None

    def test_complex_waterfall_scenario(self):
        # Arrange
        model_spec = self._create_test_model_spec("claude-3")
        model_deck = self._create_test_model_deck(
            inference_models={"claude-3": model_spec},
            llm_aliases={"premium-claude": "claude-3"},
            llm_waterfalls={"dummy-model-handle": ["premium-gpt", "premium-claude"]},
            is_model_fallback_enabled=True,
        )

        # Act
        result = model_deck.get_optional_inference_model("dummy-model-handle", model_type=ModelType.LLM)

        # Assert
        assert result == model_spec

    def test_mixed_string_and_list_aliases(self):
        # Arrange
        model_spec1 = self._create_test_model_spec("gpt-4")
        model_spec2 = self._create_test_model_spec("claude-3")
        model_deck = self._create_test_model_deck(
            inference_models={"gpt-4": model_spec1, "claude-3": model_spec2},
            llm_aliases={
                "ai-model": "best-gpt",  # string alias
            },
            llm_waterfalls={
                "best-gpt": ["gpt-4-turbo", "gpt-4"],  # list fallback
                "backup-model": ["claude-4", "claude-3"],  # list fallback
            },
            is_model_fallback_enabled=True,
        )

        # Act
        result1 = model_deck.get_optional_inference_model("ai-model", model_type=ModelType.LLM)
        result2 = model_deck.get_optional_inference_model("backup-model", model_type=ModelType.LLM)

        # Assert
        assert result1 == model_spec1  # Should resolve to gpt-4
        assert result2 == model_spec2  # Should resolve to claude-3

    @pytest.mark.parametrize(
        "llm_handle",
        [
            "",  # empty string
            "   ",  # whitespace only
            "model-with-special-chars!@#",  # special characters
            "UPPERCASE-MODEL",  # uppercase
        ],
    )
    def test_edge_case_llm_handles(self, llm_handle: str):
        # Arrange
        model_deck = self._create_test_model_deck()

        # Act
        result = model_deck.get_optional_inference_model(llm_handle, model_type=ModelType.LLM)

        # Assert
        assert result is None


class TestModelDeckPrefixedAliasReferences:
    """Tests for prefixed alias references (e.g., @alias_name) in model lookups.

    These tests verify that model references with explicit prefixes like '@best-gpt'
    are correctly resolved to their target models.
    """

    def _create_test_model_spec(self, name: str) -> InferenceModelSpec:
        return InferenceModelSpec(
            backend_name="test_backend",
            name=name,
            sdk="test_sdk",
            model_type=ModelType.LLM,
            model_id=f"test_model_{name}",
            costs={CostCategory.INPUT: 0.001, CostCategory.OUTPUT: 0.002},
            thinking_mode=ThinkingMode.NONE,
            max_tokens=1000,
            max_prompt_images=None,
        )

    def _create_test_model_deck(
        self,
        inference_models: dict[str, InferenceModelSpec] | None = None,
        llm_aliases: dict[str, str] | None = None,
        llm_waterfalls: dict[str, list[str]] | None = None,
        llm_presets: dict[str, LLMSetting] | None = None,
        is_model_fallback_enabled: bool = False,
    ) -> ModelDeck:
        return ModelDeck(
            inference_models=inference_models or {},
            # LLM-specific
            llm_default_temperature=0.7,
            llm_aliases=llm_aliases or {},
            llm_waterfalls=llm_waterfalls or {},
            llm_presets=llm_presets or {},
            llm_choice_defaults=LLMSettingChoicesDefaults(
                default_temperature=0.7,
                for_text=LLMSetting(model="default_text", temperature=0.7, max_tokens=1000),
                for_object=LLMSetting(model="default_object", temperature=0.1, max_tokens=1000),
            ),
            # Extract-specific
            extract_aliases={},
            extract_waterfalls={},
            extract_presets={},
            extract_choice_default="default-extract-document",
            # ImgGen-specific
            img_gen_default_quality=Quality.MEDIUM,
            img_gen_aliases={},
            img_gen_waterfalls={},
            img_gen_presets={},
            img_gen_choice_default="gen_image_basic",
            model_deck_config=ModelDeckConfig(is_model_fallback_enabled=is_model_fallback_enabled, missing_presets_reaction=ProblemReaction.NONE),
        )

    def test_is_model_handle_defined_with_prefixed_alias(self):
        """Test that is_model_handle_defined recognizes prefixed alias references like '@best-gpt'."""
        # Arrange
        model_spec = self._create_test_model_spec("gpt-4")
        model_deck = self._create_test_model_deck(
            inference_models={"gpt-4": model_spec},
            llm_aliases={"best-gpt": "gpt-4"},
        )

        # Act - using prefixed alias reference
        is_defined = model_deck.is_model_handle_defined(model_handle="@best-gpt", model_type=ModelType.LLM)

        # Assert - this should be True because @best-gpt refers to the alias 'best-gpt'
        assert is_defined is True

    def test_get_optional_inference_model_with_prefixed_alias(self):
        """Test that get_optional_inference_model resolves prefixed alias references like '@best-gpt'."""
        # Arrange
        model_spec = self._create_test_model_spec("gpt-4")
        model_deck = self._create_test_model_deck(
            inference_models={"gpt-4": model_spec},
            llm_aliases={"best-gpt": "gpt-4"},
        )

        # Act - using prefixed alias reference
        result = model_deck.get_optional_inference_model("@best-gpt", model_type=ModelType.LLM)

        # Assert - should resolve to the gpt-4 model spec
        assert result is not None
        assert result.name == "gpt-4"

    def test_is_model_handle_defined_with_prefixed_waterfall(self):
        """Test that is_model_handle_defined recognizes prefixed waterfall references like '~small-llm'."""
        # Arrange
        model_spec = self._create_test_model_spec("gpt-4-mini")
        model_deck = self._create_test_model_deck(
            inference_models={"gpt-4-mini": model_spec},
            llm_waterfalls={"small-llm": ["gpt-4-mini", "claude-instant"]},
            is_model_fallback_enabled=True,
        )

        # Act - using prefixed waterfall reference
        is_defined = model_deck.is_model_handle_defined(model_handle="~small-llm", model_type=ModelType.LLM)

        # Assert - this should be True because ~small-llm refers to the waterfall 'small-llm'
        assert is_defined is True

    def test_get_optional_inference_model_with_prefixed_waterfall(self):
        """Test that get_optional_inference_model resolves prefixed waterfall references like '~small-llm'."""
        # Arrange
        model_spec = self._create_test_model_spec("gpt-4-mini")
        model_deck = self._create_test_model_deck(
            inference_models={"gpt-4-mini": model_spec},
            llm_waterfalls={"small-llm": ["gpt-4-mini", "claude-instant"]},
            is_model_fallback_enabled=True,
        )

        # Act - using prefixed waterfall reference
        result = model_deck.get_optional_inference_model("~small-llm", model_type=ModelType.LLM)

        # Assert - should resolve to the first available model in the waterfall
        assert result is not None
        assert result.name == "gpt-4-mini"

    def test_validate_llm_presets_with_prefixed_alias_in_model_field(self):
        """Test that validate_llm_presets accepts presets with prefixed alias references in the model field.

        This mimics the real-world scenario where TOML presets use:
        writing-factual = { model = "@default-premium", temperature = 0.1 }
        """
        # Arrange
        model_spec = self._create_test_model_spec("gpt-4")
        preset_with_alias = LLMSetting(model="@best-gpt", temperature=0.5)
        model_deck = self._create_test_model_deck(
            inference_models={"gpt-4": model_spec},
            llm_aliases={"best-gpt": "gpt-4"},
            llm_presets={"my-preset": preset_with_alias},
        )

        # Act & Assert - should not raise an exception
        model_deck.validate_llm_presets()

    def test_validate_llm_presets_with_chained_prefixed_alias(self):
        """Test validation with presets using prefixed alias that points to another alias."""
        # Arrange
        model_spec = self._create_test_model_spec("claude-4.5-opus")
        preset_with_alias = LLMSetting(model="@default-premium", temperature=0.1)
        model_deck = self._create_test_model_deck(
            inference_models={"claude-4.5-opus": model_spec},
            llm_aliases={
                "default-premium": "claude-4.5-opus",  # this is what @default-premium should resolve to
            },
            llm_presets={"writing-factual": preset_with_alias},
        )

        # Act & Assert - should not raise an exception
        model_deck.validate_llm_presets()


class TestModelDeckGetLLMSettingWithPresets:
    """Tests for get_llm_setting() with preset references.

    These tests verify that preset names are correctly resolved whether
    passed as bare strings or with the $ prefix.
    """

    def _create_test_model_spec(self, name: str) -> InferenceModelSpec:
        return InferenceModelSpec(
            backend_name="test_backend",
            name=name,
            sdk="test_sdk",
            model_type=ModelType.LLM,
            model_id=f"test_model_{name}",
            costs={CostCategory.INPUT: 0.001, CostCategory.OUTPUT: 0.002},
            thinking_mode=ThinkingMode.NONE,
            max_tokens=1000,
            max_prompt_images=None,
        )

    def _create_test_model_deck(
        self,
        inference_models: dict[str, InferenceModelSpec] | None = None,
        llm_aliases: dict[str, str] | None = None,
        llm_presets: dict[str, LLMSetting] | None = None,
    ) -> ModelDeck:
        return ModelDeck(
            inference_models=inference_models or {},
            # LLM-specific
            llm_default_temperature=0.7,
            llm_aliases=llm_aliases or {},
            llm_waterfalls={},
            llm_presets=llm_presets or {},
            llm_choice_defaults=LLMSettingChoicesDefaults(
                default_temperature=0.7,
                for_text=LLMSetting(model="default_text", temperature=0.7, max_tokens=1000),
                for_object=LLMSetting(model="default_object", temperature=0.1, max_tokens=1000),
            ),
            # Extract-specific
            extract_aliases={},
            extract_waterfalls={},
            extract_presets={},
            extract_choice_default="default-extract-document",
            # ImgGen-specific
            img_gen_default_quality=Quality.MEDIUM,
            img_gen_aliases={},
            img_gen_waterfalls={},
            img_gen_presets={},
            img_gen_choice_default="gen_image_basic",
            model_deck_config=ModelDeckConfig(is_model_fallback_enabled=False, missing_presets_reaction=ProblemReaction.NONE),
        )

    def test_get_llm_setting_with_prefixed_preset(self):
        """Test that get_llm_setting resolves prefixed preset references like '$testing-text'."""
        # Arrange
        model_spec = self._create_test_model_spec("gpt-4")
        preset = LLMSetting(model="gpt-4", temperature=0.5, max_tokens=500)
        model_deck = self._create_test_model_deck(
            inference_models={"gpt-4": model_spec},
            llm_presets={"testing-text": preset},
        )

        # Act - using prefixed preset reference
        result = model_deck.get_llm_setting(llm_choice="$testing-text")

        # Assert - should return the preset
        assert result.model == "gpt-4"
        assert result.temperature == 0.5
        assert result.max_tokens == 500

    def test_get_llm_setting_with_bare_preset_name_fails(self):
        """Test that get_llm_setting with bare preset name (no $ prefix) fails.

        This test documents the expected behavior: bare strings are treated as
        direct model handles, not presets. Test code using bare preset names like
        "testing-text" instead of "$testing-text" will fail.
        """
        # Arrange
        model_spec = self._create_test_model_spec("gpt-4")
        preset = LLMSetting(model="gpt-4", temperature=0.5, max_tokens=500)
        model_deck = self._create_test_model_deck(
            inference_models={"gpt-4": model_spec},
            llm_presets={"testing-text": preset},
        )

        # Act & Assert - bare preset name should raise an error
        # because it's treated as a direct model handle, not a preset
        with pytest.raises(ModelChoiceNotFoundError) as excinfo:
            model_deck.get_llm_setting(llm_choice="testing-text")

        # Verify the error message indicates the name was not found as a handle
        assert "testing-text" in str(excinfo.value)
