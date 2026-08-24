from datetime import date, datetime

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

    def test_required_with_default_is_rejected_at_spec_level(self):
        """The E3 pair is rejected on the authoring surface itself, with the same two-remedies
        message as the blueprint — a builder agent must not validate green and then die on its
        own emitted TOML.
        """
        with pytest.raises(ValidationError) as exc_info:
            ConceptStructureSpec(
                the_field_name="title",
                description="A title",
                type=ConceptStructureSpecFieldType.TEXT,
                required=True,
                default_value="Untitled",
            )
        error_str = str(exc_info.value)
        assert "required" in error_str
        assert "default_value" in error_str

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

    def test_date_spec_accepts_date_rejects_datetime(self):
        """A spec `date` field accepts a calendar date and rejects a datetime (mirrors the blueprint layer)."""
        spec = ConceptStructureSpec(
            the_field_name="issued_on", description="Issue date", type=ConceptStructureSpecFieldType.DATE, default_value=date(2026, 7, 7)
        )
        assert spec.to_blueprint().type == ConceptStructureBlueprintFieldType.DATE

        with pytest.raises(ValidationError, match="default_value type mismatch: expected date"):
            ConceptStructureSpec(
                the_field_name="issued_on",
                description="Issue date",
                type=ConceptStructureSpecFieldType.DATE,
                default_value=datetime(2026, 7, 7, 15, 40),
            )

    def test_datetime_spec_type_and_to_blueprint(self):
        """A spec `datetime` field accepts a timestamp default and maps to the blueprint DATETIME type."""
        spec = ConceptStructureSpec(
            the_field_name="recorded_at",
            description="Record timestamp",
            type=ConceptStructureSpecFieldType.DATETIME,
            default_value=datetime(2026, 7, 7, 15, 40),
        )
        assert spec.to_blueprint().type == ConceptStructureBlueprintFieldType.DATETIME

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
