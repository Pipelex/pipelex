import pytest

from pipelex.builder.pipe.pipe_img_gen_spec import ImgGenSkill
from pipelex.cogt.exceptions import ModelChoiceNotFoundError
from pipelex.cogt.models.model_deck_check import check_img_gen_choice_with_deck


class TestImgGenSkill:
    """Test that all ImgGenSkill enum values are valid ImgGenModelChoice values in the model deck."""

    def test_all_img_gen_skills_are_valid_img_gen_choices(self):
        """Verify that every ImgGenSkill enum value can be resolved as a valid ImgGenModelChoice.

        This ensures that all skill-based image generation choices referenced in code are actually
        configured in the model deck (as presets, waterfalls, aliases, or direct model names)
        and available at runtime.
        """
        # Get all ImgGen skill values
        all_img_gen_skills = [skill.value for skill in ImgGenSkill]

        # Act & Assert
        invalid_choices: list[str] = []
        for skill_value in all_img_gen_skills:
            try:
                # Use check_img_gen_choice_with_deck to validate - this checks both presets and handles
                check_img_gen_choice_with_deck(skill_value)
            except ModelChoiceNotFoundError:
                invalid_choices.append(skill_value)

        # Provide clear error message if any choices are invalid
        assert not invalid_choices, (
            f"The following ImgGenSkill values are not valid image generation choices in the model deck: "
            f"{', '.join(invalid_choices)}. "
            f"Please add them as presets, waterfalls, aliases, or ensure they exist as direct model names "
            f"in .pipelex/inference/deck/base_deck.toml or overrides.toml"
        )

    def test_individual_img_gen_skills_are_valid(self):
        """Test each ImgGenSkill value individually for better error reporting."""
        for skill in ImgGenSkill:
            try:
                # Use check_img_gen_choice_with_deck to validate - this checks both presets and handles
                check_img_gen_choice_with_deck(skill.value)
            except ModelChoiceNotFoundError as e:
                pytest.fail(f"ImgGenSkill.{skill.name} ('{skill.value}') is not a valid image generation choice in the model deck. Error: {e}")
