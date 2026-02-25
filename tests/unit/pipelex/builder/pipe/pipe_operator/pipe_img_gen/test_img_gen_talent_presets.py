import pytest

from pipelex.builder.talents.img_gen_talent import ImgGenTalent
from pipelex.cogt.exceptions import ModelChoiceNotFoundError
from pipelex.cogt.models.model_deck_check import check_img_gen_choice_with_deck
from pipelex.config import get_config


class TestImgGenTalent:
    """Test that all ImgGenTalent enum values are valid ImgGenModelChoice values in the model deck."""

    def test_all_img_gen_talents_are_valid_img_gen_choices(self):
        """Verify that every ImgGenTalent enum value can be resolved as a valid ImgGenModelChoice.

        This ensures that all talent-based image generation choices referenced in code are actually
        configured in the model deck (as presets, waterfalls, aliases, or direct model names)
        and available at runtime.
        """
        # Get all ImgGen talent values
        mappings = get_config().pipelex.builder_config.talent_preset_mappings.img_gen

        # Act & Assert
        invalid_choices: list[str] = []
        for talent in ImgGenTalent:
            try:
                # Use check_img_gen_choice_with_deck to validate - this checks both presets and handles
                img_gen_choice = mappings[talent]
                check_img_gen_choice_with_deck(img_gen_choice)
            except ModelChoiceNotFoundError:
                invalid_choices.append(talent.value)

        # Provide clear error message if any choices are invalid
        assert not invalid_choices, (
            f"The following ImgGenTalent values are not valid image generation choices in the model deck: "
            f"{', '.join(invalid_choices)}. "
            f"Please add them as presets, waterfalls, aliases, or ensure they exist as direct model names "
            f"in .pipelex/inference/deck/base_deck.toml or overrides.toml"
        )

    def test_individual_img_gen_talents_are_valid(self):
        """Test each ImgGenTalent value individually for better error reporting."""
        mappings = get_config().pipelex.builder_config.talent_preset_mappings.img_gen
        for talent in ImgGenTalent:
            try:
                # Use check_img_gen_choice_with_deck to validate - this checks both presets and handles
                img_gen_choice = mappings[talent]
                check_img_gen_choice_with_deck(img_gen_choice)
            except ModelChoiceNotFoundError as exc:
                pytest.fail(f"ImgGenTalent.{talent.name} ('{talent.value}') is not a valid image generation choice in the model deck. Error: {exc}")
