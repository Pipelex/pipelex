"""Unknown keys in a structure-field table are rejected (S2 E7) — the field table's keys are
strict, exactly like an input slot table's, while hint content stays lenient (intent-hints.md).
"""

import pytest
from pydantic import ValidationError

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint


class TestConceptStructureBlueprintExtraKeys:
    @pytest.mark.parametrize(
        ("extra_key", "extra_value"),
        [
            ("minimum", 0),
            ("maximum", 100),
            ("examples", [1, 2]),
            ("unit", "items"),
            ("hint", {"intent": "label"}),
            ("defalt_value", "typo'd default"),
        ],
    )
    def test_unknown_field_key_is_rejected(self, extra_key: str, extra_value: object) -> None:
        """A hopeful or typo'd key on a structure field must fail loudly, never drop silently."""
        with pytest.raises(ValidationError) as exc_info:
            ConceptStructureBlueprint.model_validate({"description": "a field", "type": "integer", extra_key: extra_value})
        assert extra_key in str(exc_info.value)

    def test_unknown_field_key_is_rejected_through_concept_blueprint(self) -> None:
        """The rejection reaches the concept blueprint's structure table, the authoring path."""
        with pytest.raises(ValidationError):
            ConceptBlueprint.model_validate(
                {
                    "description": "a concept",
                    "structure": {"count": {"type": "integer", "description": "a count", "minimum": 0}},
                }
            )

    def test_known_keys_still_accepted(self) -> None:
        field = ConceptStructureBlueprint.model_validate(
            {
                "description": "a field",
                "type": "integer",
                "required": True,
                "hints": {"intent": "quantity"},
            }
        )
        assert field.required is True

    def test_unknown_hint_content_keys_stay_lenient(self) -> None:
        """The strictness boundary is H2's: the field table's keys are strict, hint CONTENT is not."""
        field = ConceptStructureBlueprint.model_validate(
            {
                "description": "a field",
                "type": "text",
                "hints": {"made_up_hint_key": "preserved"},
            }
        )
        assert field.hints == {"made_up_hint_key": "preserved"}
