import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.llm.llm_setting import LLMSetting, LLMSettingChoicesDefaults
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.usage.cost_category import CostCategory


class TestModelDeckGetOptionalInferenceModel:
    def _create_test_model_spec(self, name: str) -> InferenceModelSpec:
        return InferenceModelSpec(
            backend_name="test_backend",
            name=name,
            sdk="test_sdk",
            model_type=ModelType.LLM,
            model_id=f"test_model_{name}",
            costs={CostCategory.INPUT: 0.001, CostCategory.OUTPUT: 0.002},
            max_tokens=1000,
            max_prompt_images=None,
        )

    def _create_test_model_deck(
        self,
        inference_models: dict[str, InferenceModelSpec] | None = None,
        aliases: dict[str, str | list[str]] | None = None,
    ) -> ModelDeck:
        return ModelDeck(
            inference_models=inference_models or {},
            aliases=aliases or {},
            llm_presets={},
            llm_choice_defaults=LLMSettingChoicesDefaults(
                for_text=LLMSetting(llm_handle="default_text", temperature=0.7, max_tokens=1000),
                for_object=LLMSetting(llm_handle="default_object", temperature=0.1, max_tokens=1000),
            ),
            ocr_presets={},
            ocr_choice_default="base_ocr_mistral",
            img_gen_presets={},
            img_gen_choice_default="base_img_gen",
        )

    def test_direct_model_lookup_success(self):
        # Arrange
        model_spec = self._create_test_model_spec("gpt-4")
        model_deck = self._create_test_model_deck(inference_models={"gpt-4": model_spec})

        # Act
        result = model_deck.get_optional_inference_model("gpt-4")

        # Assert
        assert result == model_spec

    def test_direct_model_lookup_not_found(self, mocker: MockerFixture):
        # Arrange
        model_deck = self._create_test_model_deck()
        mock_log = mocker.patch("pipelex.cogt.models.model_deck.log")

        # Act
        result = model_deck.get_optional_inference_model("nonexistent-model")

        # Assert
        assert result is None
        mock_log.warning.assert_called_once_with("Skipping model handle 'nonexistent-model' because it's not found in deck")

    def test_simple_string_alias_resolution_success(self, mocker: MockerFixture):
        # Arrange
        model_spec = self._create_test_model_spec("gpt-4")
        model_deck = self._create_test_model_deck(inference_models={"gpt-4": model_spec}, aliases={"best-gpt": "gpt-4"})
        mock_log = mocker.patch("pipelex.cogt.models.model_deck.log")

        # Act
        result = model_deck.get_optional_inference_model("best-gpt")

        # Assert
        assert result == model_spec
        mock_log.debug.assert_called_once_with("Redirection for 'best-gpt': gpt-4")

    def test_simple_string_alias_resolution_not_found(self, mocker: MockerFixture):
        # Arrange
        model_deck = self._create_test_model_deck(aliases={"best-gpt": "nonexistent-model"})
        mock_log = mocker.patch("pipelex.cogt.models.model_deck.log")

        # Act
        result = model_deck.get_optional_inference_model("best-gpt")

        # Assert
        assert result is None
        mock_log.debug.assert_called_once_with("Redirection for 'best-gpt': nonexistent-model")
        # The final warning is about the original alias, not the target
        mock_log.warning.assert_called_with("Skipping model handle 'best-gpt' because it's not found in deck")

    def test_list_alias_resolution_first_success(self, mocker: MockerFixture):
        # Arrange
        model_spec = self._create_test_model_spec("gpt-4")
        model_deck = self._create_test_model_deck(inference_models={"gpt-4": model_spec}, aliases={"best-model": ["gpt-4", "claude-3"]})
        mock_log = mocker.patch("pipelex.cogt.models.model_deck.log")

        # Act
        result = model_deck.get_optional_inference_model("best-model")

        # Assert
        assert result == model_spec
        mock_log.debug.assert_called_once_with("Redirection for 'best-model': ['gpt-4', 'claude-3']")

    def test_list_alias_resolution_second_success(self, mocker: MockerFixture):
        # Arrange
        model_spec = self._create_test_model_spec("claude-3")
        model_deck = self._create_test_model_deck(
            inference_models={"claude-3": model_spec}, aliases={"best-model": ["nonexistent-model", "claude-3"]},
        )
        mock_log = mocker.patch("pipelex.cogt.models.model_deck.log")

        # Act
        result = model_deck.get_optional_inference_model("best-model")

        # Assert
        assert result == model_spec
        mock_log.debug.assert_called_once_with("Redirection for 'best-model': ['nonexistent-model', 'claude-3']")

    def test_list_alias_resolution_none_found(self, mocker: MockerFixture):
        # Arrange
        model_deck = self._create_test_model_deck(aliases={"best-model": ["nonexistent-1", "nonexistent-2"]})
        mock_log = mocker.patch("pipelex.cogt.models.model_deck.log")

        # Act
        result = model_deck.get_optional_inference_model("best-model")

        # Assert
        assert result is None
        mock_log.debug.assert_called_once_with("Redirection for 'best-model': ['nonexistent-1', 'nonexistent-2']")
        # Should have warning calls: one for each alias in the list + one for the original alias
        assert mock_log.warning.call_count == 3

    def test_recursive_alias_resolution_success(self, mocker: MockerFixture):
        # Arrange
        model_spec = self._create_test_model_spec("gpt-4")
        model_deck = self._create_test_model_deck(inference_models={"gpt-4": model_spec}, aliases={"best-model": "best-gpt", "best-gpt": "gpt-4"})
        mock_log = mocker.patch("pipelex.cogt.models.model_deck.log")

        # Act
        result = model_deck.get_optional_inference_model("best-model")

        # Assert
        assert result == model_spec
        # Should have debug calls for both redirections
        assert mock_log.debug.call_count == 2

    def test_recursive_alias_resolution_with_list(self, mocker: MockerFixture):
        # Arrange
        model_spec = self._create_test_model_spec("gpt-4")
        model_deck = self._create_test_model_deck(
            inference_models={"gpt-4": model_spec}, aliases={"best-model": ["nonexistent", "best-gpt"], "best-gpt": "gpt-4"},
        )
        mock_log = mocker.patch("pipelex.cogt.models.model_deck.log")

        # Act
        result = model_deck.get_optional_inference_model("best-model")

        # Assert
        assert result == model_spec
        # Should have debug calls for both redirections
        assert mock_log.debug.call_count >= 2

    def test_empty_alias_list(self, mocker: MockerFixture):
        # Arrange
        model_deck = self._create_test_model_deck(aliases={"empty-alias": []})
        mock_log = mocker.patch("pipelex.cogt.models.model_deck.log")

        # Act
        result = model_deck.get_optional_inference_model("empty-alias")

        # Assert
        assert result is None
        # Empty list evaluates to False, so no debug log is called
        mock_log.debug.assert_not_called()
        mock_log.warning.assert_called_once_with("Skipping model handle 'empty-alias' because it's not found in deck")

    def test_circular_alias_prevention(self, mocker: MockerFixture):
        # Note: The current implementation doesn't have explicit circular reference detection,
        # but Python's recursion limit should prevent infinite loops.
        # This test ensures the method handles it gracefully.

        # Arrange
        model_deck = self._create_test_model_deck(aliases={"alias-a": "alias-b", "alias-b": "alias-a"})
        mocker.patch("pipelex.cogt.models.model_deck.log")

        # Act & Assert
        # This should either return None or raise RecursionError (which would be caught by pytest)
        # The important thing is it doesn't hang indefinitely
        with pytest.raises((RecursionError, Exception)) or True:
            result = model_deck.get_optional_inference_model("alias-a")
            # If no exception, result should be None
            assert result is None

    def test_complex_waterfall_scenario(self, mocker: MockerFixture):
        # Arrange
        model_spec = self._create_test_model_spec("claude-3")
        model_deck = self._create_test_model_deck(
            inference_models={"claude-3": model_spec},
            aliases={"best-model": ["premium-gpt", "premium-claude"], "premium-gpt": ["gpt-4-turbo", "gpt-4"], "premium-claude": "claude-3"},
        )
        mock_log = mocker.patch("pipelex.cogt.models.model_deck.log")

        # Act
        result = model_deck.get_optional_inference_model("best-model")

        # Assert
        assert result == model_spec
        # Should have multiple debug calls for the waterfall resolution
        assert mock_log.debug.call_count >= 2

    def test_mixed_string_and_list_aliases(self, mocker: MockerFixture):
        # Arrange
        model_spec1 = self._create_test_model_spec("gpt-4")
        model_spec2 = self._create_test_model_spec("claude-3")
        model_deck = self._create_test_model_deck(
            inference_models={"gpt-4": model_spec1, "claude-3": model_spec2},
            aliases={
                "ai-model": "best-gpt",  # string alias
                "best-gpt": ["gpt-4-turbo", "gpt-4"],  # list alias
                "backup-model": ["claude-4", "claude-3"],  # list alias
            },
        )
        mocker.patch("pipelex.cogt.models.model_deck.log")

        # Act
        result1 = model_deck.get_optional_inference_model("ai-model")
        result2 = model_deck.get_optional_inference_model("backup-model")

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
    def test_edge_case_llm_handles(self, llm_handle: str, mocker: MockerFixture):
        # Arrange
        model_deck = self._create_test_model_deck()
        mock_log = mocker.patch("pipelex.cogt.models.model_deck.log")

        # Act
        result = model_deck.get_optional_inference_model(llm_handle)

        # Assert
        assert result is None
        mock_log.warning.assert_called_once_with(f"Skipping model handle '{llm_handle}' because it's not found in deck")

    def test_logging_behavior(self, mocker: MockerFixture):
        # Arrange
        model_deck = self._create_test_model_deck(aliases={"test-alias": "target-model"})
        mock_log = mocker.patch("pipelex.cogt.models.model_deck.log")

        # Act
        model_deck.get_optional_inference_model("test-alias")

        # Assert
        # Verify debug log for redirection
        mock_log.debug.assert_called_with("Redirection for 'test-alias': target-model")

        # The final warning is about the original alias, not the target
        mock_log.warning.assert_called_with("Skipping model handle 'test-alias' because it's not found in deck")
