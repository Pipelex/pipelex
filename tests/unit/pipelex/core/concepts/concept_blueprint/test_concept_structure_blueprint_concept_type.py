"""Tests for ConceptStructureBlueprint CONCEPT type and concept references."""

import pytest
from pydantic import ValidationError

from pipelex.core.concepts.concept_structure_blueprint import (
    ConceptStructureBlueprint,
    ConceptStructureBlueprintFieldType,
)


class TestConceptStructureBlueprintConceptType:
    """Test ConceptStructureBlueprint with CONCEPT type for concept-to-concept references."""

    def test_valid_concept_field_with_concept_ref(self):
        """Test that a concept field with concept_ref is valid."""
        blueprint = ConceptStructureBlueprint(
            description="A customer reference",
            type=ConceptStructureBlueprintFieldType.CONCEPT,
            concept_ref="myapp.Customer",
        )
        assert blueprint.type == ConceptStructureBlueprintFieldType.CONCEPT
        assert blueprint.concept_ref == "myapp.Customer"

    def test_concept_type_requires_concept_ref(self):
        """Test that concept type requires concept_ref to be set."""
        with pytest.raises(ValidationError, match="concept_ref must be set"):
            ConceptStructureBlueprint(
                description="A customer reference",
                type=ConceptStructureBlueprintFieldType.CONCEPT,
            )

    def test_concept_ref_only_valid_with_concept_type(self):
        """Test that concept_ref can only be set when type is concept."""
        with pytest.raises(ValidationError, match="'concept_ref' can only be set when type is 'concept'"):
            ConceptStructureBlueprint(
                description="A text field",
                type=ConceptStructureBlueprintFieldType.TEXT,
                concept_ref="myapp.Customer",
            )

    def test_valid_list_of_concepts(self):
        """Test that a list of concepts with item_concept_ref is valid."""
        blueprint = ConceptStructureBlueprint(
            description="A list of line items",
            type=ConceptStructureBlueprintFieldType.LIST,
            item_type="concept",
            item_concept_ref="myapp.LineItem",
        )
        assert blueprint.type == ConceptStructureBlueprintFieldType.LIST
        assert blueprint.item_type == "concept"
        assert blueprint.item_concept_ref == "myapp.LineItem"

    def test_list_of_concepts_requires_item_concept_ref(self):
        """Test that list with item_type='concept' requires item_concept_ref."""
        with pytest.raises(ValidationError, match="item_concept_ref must be set"):
            ConceptStructureBlueprint(
                description="A list of items",
                type=ConceptStructureBlueprintFieldType.LIST,
                item_type="concept",
            )

    def test_item_concept_ref_only_valid_with_concept_item_type(self):
        """Test that item_concept_ref can only be set when item_type is 'concept'."""
        with pytest.raises(ValidationError, match="item_concept_ref can only be set when item_type is 'concept'"):
            ConceptStructureBlueprint(
                description="A list of strings",
                type=ConceptStructureBlueprintFieldType.LIST,
                item_type="text",
                item_concept_ref="myapp.SomeItem",
            )

    def test_concept_ref_format_validation(self):
        """Test that concept_ref must be in domain.ConceptCode format."""
        # Valid format
        valid_blueprint = ConceptStructureBlueprint(
            description="A customer reference",
            type=ConceptStructureBlueprintFieldType.CONCEPT,
            concept_ref="myapp.Customer",
        )
        assert valid_blueprint.concept_ref == "myapp.Customer"

        # Also valid: native.Text format
        native_blueprint = ConceptStructureBlueprint(
            description="A text reference",
            type=ConceptStructureBlueprintFieldType.CONCEPT,
            concept_ref="native.Text",
        )
        assert native_blueprint.concept_ref == "native.Text"

    def test_concept_field_not_required_by_default(self):
        """Test that concept fields can be optional."""
        blueprint = ConceptStructureBlueprint(
            description="An optional customer reference",
            type=ConceptStructureBlueprintFieldType.CONCEPT,
            concept_ref="myapp.Customer",
            required=False,
        )
        assert blueprint.required is False

    def test_concept_field_cannot_have_default_value(self):
        """Test that concept fields cannot have default values (complex objects)."""
        with pytest.raises(ValidationError, match="default_value cannot be set for concept type"):
            ConceptStructureBlueprint(
                description="A customer with default",
                type=ConceptStructureBlueprintFieldType.CONCEPT,
                concept_ref="myapp.Customer",
                default_value={"name": "Default"},
            )

    def test_multiple_concept_ref_formats(self):
        """Test various valid concept_ref formats."""
        # Single domain
        single_domain = ConceptStructureBlueprint(
            description="Single domain concept",
            type=ConceptStructureBlueprintFieldType.CONCEPT,
            concept_ref="domain.Concept",
        )
        assert single_domain.concept_ref == "domain.Concept"

        # Domain with underscore
        underscore_domain = ConceptStructureBlueprint(
            description="Domain with underscore",
            type=ConceptStructureBlueprintFieldType.CONCEPT,
            concept_ref="my_domain.Concept",
        )
        assert underscore_domain.concept_ref == "my_domain.Concept"

    def test_nested_domain_concept_ref_rejected(self):
        """Test that nested domain formats (more than one dot) are rejected."""
        with pytest.raises(ValidationError, match="must be a valid concept ref"):
            ConceptStructureBlueprint(
                description="Nested domain concept",
                type=ConceptStructureBlueprintFieldType.CONCEPT,
                concept_ref="my_domain.SubDomain.Concept",
            )

    def test_list_of_concepts_can_be_optional(self):
        """Test that list of concepts can be optional."""
        blueprint = ConceptStructureBlueprint(
            description="Optional list of line items",
            type=ConceptStructureBlueprintFieldType.LIST,
            item_type="concept",
            item_concept_ref="myapp.LineItem",
            required=False,
        )
        assert blueprint.required is False
