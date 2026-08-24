"""`required = true` + `default_value` on one structure field is rejected (S2 E3) — a default
makes absence legal, which contradicts requiring the field. Two contradictory instructions on
one field is an authoring error, and it must fail loudly, never tiebreak silently.
"""

import pytest
from pydantic import ValidationError

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint


class TestConceptStructureBlueprintRequiredDefault:
    @pytest.mark.parametrize(
        "field_table",
        [
            {"description": "a field", "type": "text", "required": True, "default_value": "hello"},
            {"description": "a field", "type": "integer", "required": True, "default_value": 42},
            {"description": "a field", "choices": ["one", "two"], "required": True, "default_value": "one"},
        ],
    )
    def test_required_with_default_is_rejected(self, field_table: dict[str, object]) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ConceptStructureBlueprint.model_validate(field_table)
        assert "required" in str(exc_info.value)
        assert "default_value" in str(exc_info.value)

    def test_rejection_reaches_the_concept_blueprint(self) -> None:
        """The rejection fires on the authoring path, through the concept's structure table."""
        with pytest.raises(ValidationError):
            ConceptBlueprint.model_validate(
                {
                    "description": "a concept",
                    "structure": {"title": {"type": "text", "description": "a title", "required": True, "default_value": "Untitled"}},
                }
            )

    def test_default_without_required_still_accepted(self) -> None:
        field = ConceptStructureBlueprint.model_validate({"description": "a field", "type": "text", "default_value": "hello"})
        assert field.required is False
        assert field.default_value == "hello"

    def test_required_without_default_still_accepted(self) -> None:
        field = ConceptStructureBlueprint.model_validate({"description": "a field", "type": "text", "required": True})
        assert field.required is True
        assert field.default_value is None
