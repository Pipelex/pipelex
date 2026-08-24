"""Intent hints on the concept and structure-field sites (spec: intent-hints.md): strict shape,
lenient content, empty-table normalization, and fingerprint-neutral serialization.
"""

import json

import pytest
from pydantic import ValidationError

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType


class TestConceptBlueprintHints:
    def test_flat_table_is_accepted(self):
        blueprint = ConceptBlueprint(description="an essay", hints={"intent": "prose"})
        assert blueprint.hints == {"intent": "prose"}

    def test_unknown_key_is_preserved(self):
        blueprint = ConceptBlueprint(description="a thing", hints={"emphasis": "strong"})
        assert blueprint.hints == {"emphasis": "strong"}

    def test_empty_table_normalizes_to_absence(self):
        blueprint = ConceptBlueprint(description="a thing", hints={})
        assert blueprint.hints is None

    def test_hints_keys_are_sorted(self):
        blueprint = ConceptBlueprint(description="a thing", hints={"zeta": "z", "alpha": "a"})
        assert list(blueprint.hints or {}) == ["alpha", "zeta"]

    def test_non_table_hints_are_rejected(self):
        with pytest.raises(ValidationError):
            ConceptBlueprint.model_validate({"description": "a thing", "hints": "prose"})

    def test_non_string_value_is_rejected(self):
        with pytest.raises(ValidationError):
            ConceptBlueprint.model_validate({"description": "a thing", "hints": {"intent": 3}})

    def test_nested_table_is_rejected(self):
        with pytest.raises(ValidationError):
            ConceptBlueprint.model_validate({"description": "a thing", "hints": {"intent": {"word": "prose"}}})


class TestStructureFieldHints:
    def test_flat_table_is_accepted(self):
        field = ConceptStructureBlueprint(description="a text field", type=ConceptStructureBlueprintFieldType.TEXT, hints={"intent": "label"})
        assert field.hints == {"intent": "label"}

    def test_empty_table_normalizes_to_absence(self):
        field = ConceptStructureBlueprint(description="a text field", type=ConceptStructureBlueprintFieldType.TEXT, hints={})
        assert field.hints is None

    def test_non_table_hints_are_rejected(self):
        with pytest.raises(ValidationError):
            ConceptStructureBlueprint.model_validate({"description": "a text field", "type": "text", "hints": "label"})

    def test_non_string_value_is_rejected(self):
        with pytest.raises(ValidationError):
            ConceptStructureBlueprint.model_validate({"description": "a text field", "type": "text", "hints": {"intent": 5}})

    def test_nested_table_is_rejected(self):
        with pytest.raises(ValidationError):
            ConceptStructureBlueprint.model_validate({"description": "a text field", "type": "text", "hints": {"a": {"b": "c"}}})


class TestHintFreeSerialization:
    def test_hint_free_concept_serializes_without_hints_key_at_any_depth(self):
        blueprint = ConceptBlueprint(
            description="a structured concept",
            structure={
                "title": ConceptStructureBlueprint(description="the title", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
                "note": "a shorthand field",
            },
        )
        assert '"hints"' not in json.dumps(blueprint.model_dump(mode="json"))

    def test_hinted_concept_serializes_hints(self):
        blueprint = ConceptBlueprint(description="an essay", hints={"intent": "prose"})
        assert blueprint.model_dump(mode="json")["hints"] == {"intent": "prose"}

    def test_hinted_field_serializes_hints(self):
        field = ConceptStructureBlueprint(description="a text field", type=ConceptStructureBlueprintFieldType.TEXT, hints={"intent": "label"})
        assert field.model_dump(mode="json")["hints"] == {"intent": "label"}
