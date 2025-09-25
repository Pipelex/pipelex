"""Tests for ConceptStructureBlueprint validation logic."""

import pytest

from pipelex.core.concepts.concept_blueprint import (
    ConceptStructureBlueprint,
    ConceptStructureBlueprintError,
    ConceptStructureBlueprintFieldType,
)


class TestConceptStructureBlueprintValidation:
    """Test ConceptStructureBlueprint validation logic."""

    def test_valid_structure_blueprints(self):
        """Test that valid structure blueprints are accepted."""
        # Valid text field with default
        text_blueprint = ConceptStructureBlueprint(
            definition="A text field", type=ConceptStructureBlueprintFieldType.TEXT, default_value="default text",
        )
        assert text_blueprint.default_value == "default text"

        # Valid integer field with default
        int_blueprint = ConceptStructureBlueprint(definition="An integer field", type=ConceptStructureBlueprintFieldType.INTEGER, default_value=42)
        assert int_blueprint.default_value == 42

        # Valid boolean field with default
        bool_blueprint = ConceptStructureBlueprint(definition="A boolean field", type=ConceptStructureBlueprintFieldType.BOOLEAN, default_value=True)
        assert bool_blueprint.default_value is True

        # Valid number field with int default
        number_blueprint = ConceptStructureBlueprint(definition="A number field", type=ConceptStructureBlueprintFieldType.NUMBER, default_value=42)
        assert number_blueprint.default_value == 42

        # Valid number field with float default
        float_blueprint = ConceptStructureBlueprint(definition="A number field", type=ConceptStructureBlueprintFieldType.NUMBER, default_value=3.14)
        assert float_blueprint.default_value == 3.14

        # Valid list field with default
        list_blueprint = ConceptStructureBlueprint(
            definition="A list field", type=ConceptStructureBlueprintFieldType.LIST, item_type="text", default_value=["item1", "item2"],
        )
        assert list_blueprint.default_value == ["item1", "item2"]

    # Valid dict field with default
    dict_blueprint = ConceptStructureBlueprint(
        definition="A dict field",
        type=ConceptStructureBlueprintFieldType.DICT,
        key_type="text",
        value_type="text",
        default_value={"key": "value"},
    )
    assert dict_blueprint.default_value == {"key": "value"}

    # Valid choice field with default
    choice_blueprint = ConceptStructureBlueprint(definition="A choice field", choices=["low", "medium", "high"], default_value="medium")
    assert choice_blueprint.default_value == "medium"

    def test_default_value_type_mismatch(self):
        """Test that default_value type mismatches are caught."""
        # Text field with non-string default
        with pytest.raises(ConceptStructureBlueprintError, match="default_value type mismatch: expected str"):
            ConceptStructureBlueprint(definition="A text field", type=ConceptStructureBlueprintFieldType.TEXT, default_value=42)

        # Integer field with non-integer default
        with pytest.raises(ConceptStructureBlueprintError, match="default_value type mismatch: expected int"):
            ConceptStructureBlueprint(definition="An integer field", type=ConceptStructureBlueprintFieldType.INTEGER, default_value="not an int")

        # Boolean field with non-boolean default
        with pytest.raises(ConceptStructureBlueprintError, match="default_value type mismatch: expected bool"):
            ConceptStructureBlueprint(definition="A boolean field", type=ConceptStructureBlueprintFieldType.BOOLEAN, default_value="not a bool")

        # Number field with invalid type
        with pytest.raises(ConceptStructureBlueprintError, match="default_value type mismatch: expected number"):
            ConceptStructureBlueprint(definition="A number field", type=ConceptStructureBlueprintFieldType.NUMBER, default_value="not a number")

        # List field with non-list default
        with pytest.raises(ConceptStructureBlueprintError, match="default_value type mismatch: expected list"):
            ConceptStructureBlueprint(
                definition="A list field", type=ConceptStructureBlueprintFieldType.LIST, item_type="text", default_value="not a list",
            )

        # Dict field with non-dict default
        with pytest.raises(ConceptStructureBlueprintError, match="default_value type mismatch: expected dict"):
            ConceptStructureBlueprint(
                definition="A dict field",
                type=ConceptStructureBlueprintFieldType.DICT,
                key_type="text",
                value_type="text",
                default_value="not a dict",
            )

    def test_missing_type_with_default_value(self):
        """Test that missing type when default_value is provided (except for choices) is caught."""
        # Missing type with default_value (no choices) - this will trigger the "type is None (array)" validation first
        with pytest.raises(ConceptStructureBlueprintError, match="When type is None \\(array\\), choices must not be empty"):
            ConceptStructureBlueprint(definition="A field without type", default_value="some value")

    def test_default_value_without_type_but_with_choices_allowed(self):
        """Test that default_value with choices but no type is allowed (choice fields)."""
        # This should work - choice fields can have default_value without explicit type
        choice_blueprint = ConceptStructureBlueprint(definition="A choice field", choices=["option1", "option2", "option3"], default_value="option2")
        assert choice_blueprint.default_value == "option2"
        assert choice_blueprint.type is None
        assert choice_blueprint.choices == ["option1", "option2", "option3"]

    def test_invalid_choice_default_value(self):
        """Test that invalid default_value for choice fields is caught."""
        # Invalid choice default
        with pytest.raises(ConceptStructureBlueprintError, match="default_value must be one of the valid choices"):
            ConceptStructureBlueprint(definition="A choice field", choices=["low", "medium", "high"], default_value="invalid_choice")

    def test_existing_validations_still_work(self):
        """Test that existing validations continue to work."""
        # Type None (array) without choices
        with pytest.raises(ConceptStructureBlueprintError, match="When type is None \\(array\\), choices must not be empty"):
            ConceptStructureBlueprint(definition="Array field without choices", type=None)

        # Dict type without key_type
        with pytest.raises(ConceptStructureBlueprintError, match="key_type must not be empty"):
            ConceptStructureBlueprint(definition="Dict field without key_type", type=ConceptStructureBlueprintFieldType.DICT, value_type="text")

        # Dict type without value_type
        with pytest.raises(ConceptStructureBlueprintError, match="value_type must not be empty"):
            ConceptStructureBlueprint(definition="Dict field without value_type", type=ConceptStructureBlueprintFieldType.DICT, key_type="text")

    def test_edge_cases(self):
        """Test edge cases for validation."""
        # Valid field without default_value
        valid_blueprint = ConceptStructureBlueprint(definition="A field without default", type=ConceptStructureBlueprintFieldType.TEXT)
        assert valid_blueprint.default_value is None

        # Valid choice field without default_value
        choice_blueprint = ConceptStructureBlueprint(definition="A choice field without default", choices=["option1", "option2"])
        assert choice_blueprint.default_value is None

        # Boolean field with False default (should be valid)
        bool_false_blueprint = ConceptStructureBlueprint(
            definition="Boolean field with False default", type=ConceptStructureBlueprintFieldType.BOOLEAN, default_value=False,
        )
        assert bool_false_blueprint.default_value is False

        # Integer field with 0 default (should be valid)
        int_zero_blueprint = ConceptStructureBlueprint(
            definition="Integer field with 0 default", type=ConceptStructureBlueprintFieldType.INTEGER, default_value=0,
        )
        assert int_zero_blueprint.default_value == 0

        # Empty list as default (should be valid)
        empty_list_blueprint = ConceptStructureBlueprint(
            definition="List field with empty default", type=ConceptStructureBlueprintFieldType.LIST, item_type="text", default_value=[],
        )
        assert not empty_list_blueprint.default_value

        # Empty dict as default (should be valid)
        empty_dict_blueprint = ConceptStructureBlueprint(
            definition="Dict field with empty default",
            type=ConceptStructureBlueprintFieldType.DICT,
            key_type="text",
            value_type="text",
            default_value={},
        )
        assert not empty_dict_blueprint.default_value
