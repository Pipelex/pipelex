"""Tests for ConceptBlueprint refines field validation."""

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint


class TestConceptBlueprintRefinesValidation:
    """Test ConceptBlueprint refines field validator calls is_concept_ref_or_code_valid."""

    def test_refines_calls_is_concept_ref_or_code_valid(self, mocker: MockerFixture):
        """Test that the refines field validator calls is_concept_ref_or_code_valid."""
        mock_validator = mocker.patch(
            "pipelex.core.concepts.concept_blueprint.is_concept_ref_or_code_valid",
            return_value=True,
        )

        ConceptBlueprint(
            description="A concept that refines Text",
            refines="native.Text",
        )

        mock_validator.assert_called_once_with(concept_ref_or_code="native.Text")

    def test_refines_none_does_not_call_validator(self, mocker: MockerFixture):
        """Test that None refines skips the validator call."""
        mock_validator = mocker.patch(
            "pipelex.core.concepts.concept_blueprint.is_concept_ref_or_code_valid",
            return_value=True,
        )

        ConceptBlueprint(
            description="A concept without refines",
            refines=None,
        )

        mock_validator.assert_not_called()

    def test_refines_raises_when_validator_returns_false(self, mocker: MockerFixture):
        """Test that invalid refines raises ValidationError when validator returns False."""
        mocker.patch(
            "pipelex.core.concepts.concept_blueprint.is_concept_ref_or_code_valid",
            return_value=False,
        )

        with pytest.raises(ValidationError, match="must be a valid concept ref"):
            ConceptBlueprint(
                description="A concept with invalid refines",
                refines="invalid",
            )

    def test_refines_mutually_exclusive_with_structure(self):
        """Test that refines and structure cannot both be set."""
        with pytest.raises(ValidationError, match="cannot have both 'refines' and 'structure'"):
            ConceptBlueprint(
                description="A concept with both refines and structure",
                refines="native.Text",
                structure={
                    "field1": "A field description",
                },
            )
