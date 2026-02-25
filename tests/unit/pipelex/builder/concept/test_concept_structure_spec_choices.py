from typing import Any

import pytest
from pydantic import ValidationError

from pipelex import log
from pipelex.builder.concept.concept_spec import ConceptStructureSpec, ConceptStructureSpecFieldType
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprintFieldType
from tests.unit.pipelex.builder.concept.test_data import ConceptStructureSpecChoicesTestCases


class TestConceptStructureSpecChoices:
    """Tests for choices field behavior in ConceptStructureSpec."""

    @pytest.mark.parametrize(
        ("topic", "spec_data", "expected_type", "expected_choices"),
        ConceptStructureSpecChoicesTestCases.VALID_CASES,
    )
    def test_valid_choices(
        self,
        topic: str,
        spec_data: dict[str, Any],
        expected_type: ConceptStructureSpecFieldType,
        expected_choices: list[str],
    ) -> None:
        """Choices with compatible types should be accepted, defaulting to TEXT when type is omitted."""
        spec = ConceptStructureSpec.model_validate(spec_data)
        assert spec.type == expected_type
        assert spec.choices == expected_choices
        log.verbose(f"[{topic}] spec.type={spec.type}, spec.choices={spec.choices}")

    def test_choices_without_type_converts_to_blueprint(self) -> None:
        """Choices without explicit type should default to TEXT and convert to blueprint correctly."""
        spec = ConceptStructureSpec.model_validate(
            {
                "the_field_name": "status",
                "description": "Order status",
                "choices": ["pending", "processing", "completed"],
                "required": True,
            }
        )
        blueprint = spec.to_blueprint()
        assert blueprint.type == ConceptStructureBlueprintFieldType.TEXT
        assert blueprint.choices == ["pending", "processing", "completed"]
        log.verbose(f"Blueprint: type={blueprint.type}, choices={blueprint.choices}")

    def test_no_type_no_choices_fails_validation(self) -> None:
        """Missing type without choices should still fail validation."""
        with pytest.raises(ValidationError):
            ConceptStructureSpec.model_validate(
                {
                    "the_field_name": "name",
                    "description": "A name field",
                }
            )

    @pytest.mark.parametrize(
        ("topic", "spec_data"),
        ConceptStructureSpecChoicesTestCases.INCOMPATIBLE_CASES,
    )
    def test_incompatible_type_with_choices(
        self,
        topic: str,
        spec_data: dict[str, Any],
    ) -> None:
        """Choices with incompatible types (boolean, date, concept, list) should raise validation errors."""
        with pytest.raises(ValidationError) as exc_info:
            ConceptStructureSpec.model_validate(spec_data)
        error_str = str(exc_info.value)
        assert "choices" in error_str.lower()
        log.verbose(f"[{topic}] Validation error: {error_str}")
