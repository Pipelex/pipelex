import pytest

from pipelex.builder.pipe.pipe_llm_spec import LLMSkill
from pipelex.cogt.exceptions import ModelChoiceNotFoundError
from pipelex.cogt.models.model_deck_check import check_llm_choice_with_deck


class TestLLMSkill:
    """Test that all LLMSkill enum values are valid LLMModelChoice values in the model deck."""

    def test_all_llm_skills_are_valid_llm_choices(self):
        """Verify that every LLMSkill enum value can be resolved as a valid LLMModelChoice.

        This ensures that all skill-based LLM choices referenced in code are actually
        configured in the model deck (as presets, waterfalls, aliases, or direct model names)
        and available at runtime.
        """
        # Get all LLM skill values
        all_llm_skills = [skill.value for skill in LLMSkill]

        # Act & Assert
        invalid_choices: list[str] = []
        for skill_value in all_llm_skills:
            try:
                # Use check_llm_choice_with_deck to validate - this checks both presets and handles (including waterfalls)
                check_llm_choice_with_deck(skill_value)
            except ModelChoiceNotFoundError:
                invalid_choices.append(skill_value)

        # Provide clear error message if any choices are invalid
        assert not invalid_choices, (
            f"The following LLMSkill values are not valid LLM choices in the model deck: "
            f"{', '.join(invalid_choices)}. "
            f"Please add them as presets, waterfalls, aliases, or ensure they exist as direct model names "
            f"in .pipelex/inference/deck/base_deck.toml or overrides.toml"
        )

    def test_individual_llm_skills_are_valid(self):
        """Test each LLMSkill value individually for better error reporting."""
        for skill in LLMSkill:
            try:
                # Use check_llm_choice_with_deck to validate - this checks both presets and handles (including waterfalls)
                check_llm_choice_with_deck(skill.value)
            except ModelChoiceNotFoundError as e:
                pytest.fail(f"LLMSkill.{skill.name} ('{skill.value}') is not a valid LLM choice in the model deck. Error: {e}")
