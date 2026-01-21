import pytest
from pydantic import ValidationError

from pipelex import log
from pipelex.builder.concept.concept_spec import ConceptStructureSpec, ConceptStructureSpecFieldType


class TestConceptStructureSpecValidation:
    """Tests for validation of ConceptStructureSpec with new field types (CONCEPT, LIST)."""

    def test_concept_type_requires_concept_ref(self):
        """CONCEPT type must have concept_ref set."""
        with pytest.raises(ValidationError) as exc_info:
            ConceptStructureSpec(
                the_field_name="customer",
                description="The customer",
                type=ConceptStructureSpecFieldType.CONCEPT,
                required=True,
            )
        assert "concept_ref must be set" in str(exc_info.value)

    def test_concept_type_with_concept_ref_valid(self):
        """CONCEPT type with concept_ref is valid."""
        spec = ConceptStructureSpec(
            the_field_name="customer",
            description="The customer",
            type=ConceptStructureSpecFieldType.CONCEPT,
            concept_ref="myapp.Customer",
            required=True,
        )
        assert spec.type == ConceptStructureSpecFieldType.CONCEPT
        assert spec.concept_ref == "myapp.Customer"

    def test_concept_type_cannot_have_default_value(self):
        """CONCEPT type cannot have default_value set."""
        with pytest.raises(ValidationError) as exc_info:
            ConceptStructureSpec(
                the_field_name="customer",
                description="The customer",
                type=ConceptStructureSpecFieldType.CONCEPT,
                concept_ref="myapp.Customer",
                default_value={"name": "test"},
            )
        assert "cannot be set for concept type" in str(exc_info.value)

    def test_concept_ref_only_allowed_for_concept_type(self):
        """concept_ref can only be set when type is CONCEPT."""
        with pytest.raises(ValidationError) as exc_info:
            ConceptStructureSpec(
                the_field_name="name",
                description="The name",
                type=ConceptStructureSpecFieldType.TEXT,
                concept_ref="myapp.Customer",
            )
        error_str = str(exc_info.value)
        assert "concept_ref" in error_str
        assert "type is 'concept'" in error_str

    def test_list_type_requires_item_type(self):
        """LIST type must have item_type set."""
        with pytest.raises(ValidationError) as exc_info:
            ConceptStructureSpec(
                the_field_name="items",
                description="The items",
                type=ConceptStructureSpecFieldType.LIST,
                required=True,
            )
        assert "item_type must be set" in str(exc_info.value)

    def test_list_type_with_item_type_text_valid(self):
        """LIST type with item_type='text' is valid."""
        spec = ConceptStructureSpec(
            the_field_name="tags",
            description="List of tags",
            type=ConceptStructureSpecFieldType.LIST,
            item_type="text",
            required=False,
        )
        assert spec.type == ConceptStructureSpecFieldType.LIST
        assert spec.item_type == "text"

    def test_list_type_with_item_type_concept_requires_item_concept_ref(self):
        """LIST type with item_type='concept' must have item_concept_ref set."""
        with pytest.raises(ValidationError) as exc_info:
            ConceptStructureSpec(
                the_field_name="items",
                description="List of items",
                type=ConceptStructureSpecFieldType.LIST,
                item_type="concept",
                required=True,
            )
        assert "item_concept_ref must be set" in str(exc_info.value)

    def test_list_type_with_item_type_concept_and_item_concept_ref_valid(self):
        """LIST type with item_type='concept' and item_concept_ref is valid."""
        spec = ConceptStructureSpec(
            the_field_name="line_items",
            description="List of line items",
            type=ConceptStructureSpecFieldType.LIST,
            item_type="concept",
            item_concept_ref="myapp.LineItem",
            required=True,
        )
        assert spec.type == ConceptStructureSpecFieldType.LIST
        assert spec.item_type == "concept"
        assert spec.item_concept_ref == "myapp.LineItem"

    def test_item_concept_ref_only_allowed_with_item_type_concept(self):
        """item_concept_ref can only be set when item_type='concept'."""
        with pytest.raises(ValidationError) as exc_info:
            ConceptStructureSpec(
                the_field_name="tags",
                description="List of tags",
                type=ConceptStructureSpecFieldType.LIST,
                item_type="text",
                item_concept_ref="myapp.SomeType",
            )
        assert "item_concept_ref can only be set when item_type is 'concept'" in str(exc_info.value)

    def test_list_type_default_value_must_be_list(self):
        """LIST type default_value must be a list."""
        with pytest.raises(ValidationError) as exc_info:
            ConceptStructureSpec(
                the_field_name="tags",
                description="List of tags",
                type=ConceptStructureSpecFieldType.LIST,
                item_type="text",
                default_value="not a list",
            )
        assert "expected list" in str(exc_info.value)

    def test_list_type_with_valid_default_value(self):
        """LIST type with list default_value is valid."""
        spec = ConceptStructureSpec(
            the_field_name="tags",
            description="List of tags",
            type=ConceptStructureSpecFieldType.LIST,
            item_type="text",
            default_value=["tag1", "tag2"],
        )
        assert spec.default_value == ["tag1", "tag2"]

    def test_to_blueprint_concept_type(self):
        """Test to_blueprint() conversion for CONCEPT type."""
        spec = ConceptStructureSpec(
            the_field_name="customer",
            description="The customer",
            type=ConceptStructureSpecFieldType.CONCEPT,
            concept_ref="myapp.Customer",
            required=True,
        )
        blueprint = spec.to_blueprint()
        assert blueprint.type is not None
        assert blueprint.type.value == "concept"
        assert blueprint.concept_ref == "myapp.Customer"
        log.verbose(f"Blueprint: {blueprint}")

    def test_to_blueprint_list_type_with_concept(self):
        """Test to_blueprint() conversion for LIST type with concept items."""
        spec = ConceptStructureSpec(
            the_field_name="line_items",
            description="List of line items",
            type=ConceptStructureSpecFieldType.LIST,
            item_type="concept",
            item_concept_ref="myapp.LineItem",
            required=True,
        )
        blueprint = spec.to_blueprint()
        assert blueprint.type is not None
        assert blueprint.type.value == "list"
        assert blueprint.item_type == "concept"
        assert blueprint.item_concept_ref == "myapp.LineItem"
        log.verbose(f"Blueprint: {blueprint}")
