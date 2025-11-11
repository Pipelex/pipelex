import pytest

from pipelex.builder.pipe.pipe_extract_spec import ExtractSkill
from pipelex.cogt.exceptions import ModelChoiceNotFoundError
from pipelex.cogt.models.model_deck_check import check_extract_choice_with_deck


class TestExtractSkill:
    """Test that all ExtractSkill enum values are valid ExtractModelChoice values in the model deck."""

    def test_all_extract_skills_are_valid_extract_choices(self):
        """Verify that every ExtractSkill enum value can be resolved as a valid ExtractModelChoice.

        This ensures that all skill-based extraction choices referenced in code are actually
        configured in the model deck (as presets, waterfalls, aliases, or direct model names)
        and available at runtime.
        """
        # Get all Extract skill values
        all_extract_skills = [skill.value for skill in ExtractSkill]

        # Act & Assert
        invalid_choices: list[str] = []
        for skill_value in all_extract_skills:
            try:
                # Use check_extract_choice_with_deck to validate - this checks both presets and handles
                check_extract_choice_with_deck(skill_value)
            except ModelChoiceNotFoundError:
                invalid_choices.append(skill_value)

        # Provide clear error message if any choices are invalid
        assert not invalid_choices, (
            f"The following ExtractSkill values are not valid extraction choices in the model deck: "
            f"{', '.join(invalid_choices)}. "
            f"Please add them as presets, waterfalls, aliases, or ensure they exist as direct model names "
            f"in .pipelex/inference/deck/base_deck.toml or overrides.toml"
        )

    def test_individual_extract_skills_are_valid(self):
        """Test each ExtractSkill value individually for better error reporting."""
        for skill in ExtractSkill:
            try:
                # Use check_extract_choice_with_deck to validate - this checks both presets and handles
                check_extract_choice_with_deck(skill.value)
            except ModelChoiceNotFoundError as e:
                pytest.fail(f"ExtractSkill.{skill.name} ('{skill.value}') is not a valid extraction choice in the model deck. Error: {e}")
