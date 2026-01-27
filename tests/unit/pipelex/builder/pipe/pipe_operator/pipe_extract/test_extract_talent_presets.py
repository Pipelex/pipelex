import pytest

from pipelex.builder.talents.extract_talent import ExtractTalent
from pipelex.cogt.exceptions import ModelChoiceNotFoundError
from pipelex.cogt.models.model_deck_check import check_extract_choice_with_deck
from pipelex.config import get_config


class TestExtractTalent:
    """Test that all ExtractTalent enum values are valid ExtractModelChoice values in the model deck."""

    def test_all_extract_talents_are_valid_extract_choices(self):
        """Verify that every ExtractTalent enum value can be resolved as a valid ExtractModelChoice.

        This ensures that all talent-based extraction choices referenced in code are actually
        configured in the model deck (as presets, waterfalls, aliases, or direct model names)
        and available at runtime.
        """
        # Get all Extract talent values
        mappings = get_config().pipelex.builder_config.talent_preset_mappings.extract

        # Act & Assert
        invalid_choices: list[str] = []
        for talent in ExtractTalent:
            try:
                # Use check_extract_choice_with_deck to validate - this checks both presets and handles
                extract_choice = mappings[talent]
                check_extract_choice_with_deck(extract_choice)
            except ModelChoiceNotFoundError:
                invalid_choices.append(talent.value)

        # Provide clear error message if any choices are invalid
        assert not invalid_choices, (
            f"The following ExtractTalent values are not valid extraction choices in the model deck: "
            f"{', '.join(invalid_choices)}. "
            f"Please add them as presets, waterfalls, aliases, or ensure they exist as direct model names "
            f"in .pipelex/inference/deck/base_deck.toml or overrides.toml"
        )

    def test_individual_extract_talents_are_valid(self):
        """Test each ExtractTalent value individually for better error reporting."""
        mappings = get_config().pipelex.builder_config.talent_preset_mappings.extract
        for talent in ExtractTalent:
            try:
                # Use check_extract_choice_with_deck to validate - this checks both presets and handles
                extract_choice = mappings[talent]
                check_extract_choice_with_deck(extract_choice)
            except ModelChoiceNotFoundError as exc:
                pytest.fail(f"ExtractTalent.{talent.name} ('{talent.value}') is not a valid extraction choice in the model deck. Error: {exc}")
