import pytest
from pydantic import ValidationError

from pipelex import log
from pipelex.builder.concept.concept_spec import ConceptStructureSpec, ConceptStructureSpecFieldType
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprintFieldType


class TestConceptStructureSpecValidation:
    """Tests for validation of ConceptStructureSpec with CONCEPT field type."""

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
        assert blueprint.type == ConceptStructureBlueprintFieldType.CONCEPT
        assert blueprint.concept_ref == "myapp.Customer"
        log.verbose(f"Blueprint: {blueprint}")
