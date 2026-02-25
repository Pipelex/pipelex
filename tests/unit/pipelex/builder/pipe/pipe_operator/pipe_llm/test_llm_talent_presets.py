import pytest

from pipelex.builder.talents.llm_talent import LLMTalent
from pipelex.cogt.exceptions import ModelChoiceNotFoundError
from pipelex.cogt.models.model_deck_check import check_llm_choice_with_deck
from pipelex.config import get_config


class TestLLMTalent:
    """Test that all LLMTalent enum values are valid LLMModelChoice values in the model deck."""

    def test_all_llm_talents_are_valid_llm_choices(self):
        """Verify that every LLMTalent enum value can be resolved as a valid LLMModelChoice.

        This ensures that all talent-based LLM choices referenced in code are actually
        configured in the model deck (as presets, waterfalls, aliases, or direct model names)
        and available at runtime.
        """
        # Act & Assert
        invalid_choices: list[str] = []
        mappings = get_config().pipelex.builder_config.talent_preset_mappings.llm
        for talent in LLMTalent:
            try:
                # Use check_llm_choice_with_deck to validate - this checks both presets and handles (including waterfalls)
                llm_choice = mappings[talent]
                check_llm_choice_with_deck(llm_choice)
            except ModelChoiceNotFoundError:
                invalid_choices.append(talent.value)

        # Provide clear error message if any choices are invalid
        assert not invalid_choices, (
            f"The following LLMTalent values are not valid LLM choices in the model deck: "
            f"{', '.join(invalid_choices)}. "
            f"Please add them as presets, waterfalls, aliases, or ensure they exist as direct model names "
            f"in .pipelex/inference/deck/base_deck.toml or overrides.toml"
        )

    def test_individual_llm_talents_are_valid(self):
        """Test each LLMTalent value individually for better error reporting."""
        mappings = get_config().pipelex.builder_config.talent_preset_mappings.llm
        for talent in LLMTalent:
            try:
                # Use check_llm_choice_with_deck to validate - this checks both presets and handles (including waterfalls)
                llm_choice = mappings[talent]
                check_llm_choice_with_deck(llm_choice)
            except ModelChoiceNotFoundError as exc:
                pytest.fail(f"LLMTalent.{talent.name} ('{talent.value}') is not a valid LLM choice in the model deck. Error: {exc}")
