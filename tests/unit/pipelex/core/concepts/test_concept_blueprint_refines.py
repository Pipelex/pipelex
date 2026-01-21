"""Tests for ConceptBlueprint refines validation with non-native concepts."""

import pytest
from pydantic import ValidationError

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint


class TestConceptBlueprintRefinesValidation:
    """Test ConceptBlueprint refines validation for both native and non-native concepts."""

    def test_refines_native_concept_code(self):
        """Test that native concept codes are accepted."""
        blueprint = ConceptBlueprint(
            description="A concept that refines Text",
            refines="Text",
        )
        assert blueprint.refines == "Text"

    def test_refines_native_concept_ref(self):
        """Test that native concept refs with native. prefix are accepted."""
        blueprint = ConceptBlueprint(
            description="A concept that refines native.Text",
            refines="native.Text",
        )
        assert blueprint.refines == "native.Text"

    def test_refines_native_image_concept(self):
        """Test that native Image concept is accepted."""
        blueprint = ConceptBlueprint(
            description="A concept that refines Image",
            refines="Image",
        )
        assert blueprint.refines == "Image"

    def test_refines_non_native_concept_ref(self):
        """Test that non-native concept refs in domain.ConceptCode format are accepted."""
        blueprint = ConceptBlueprint(
            description="A concept that refines another custom concept",
            refines="myapp.BaseEntity",
        )
        assert blueprint.refines == "myapp.BaseEntity"

    def test_refines_cross_domain_concept_ref(self):
        """Test that cross-domain concept refs are accepted."""
        blueprint = ConceptBlueprint(
            description="A concept that refines a concept from another domain",
            refines="crm.Customer",
        )
        assert blueprint.refines == "crm.Customer"

    def test_refines_deeply_nested_domain_rejected(self):
        """Test that deeply nested domain concept refs are rejected (only domain.ConceptCode allowed)."""
        with pytest.raises(ValidationError, match="must be a valid concept ref"):
            ConceptBlueprint(
                description="A concept with deeply nested domain",
                refines="org.dept.team.Entity",
            )

    def test_refines_none_is_valid(self):
        """Test that None refines is valid (no inheritance)."""
        blueprint = ConceptBlueprint(
            description="A concept without refines",
            refines=None,
        )
        assert blueprint.refines is None

    def test_refines_bare_pascal_case_code_accepted(self):
        """Test that bare PascalCase concept codes are accepted (valid concept code)."""
        blueprint = ConceptBlueprint(
            description="A concept with PascalCase refines",
            refines="SomeCustomConcept",
        )
        assert blueprint.refines == "SomeCustomConcept"

    def test_refines_invalid_lowercase_bare_code_rejected(self):
        """Test that lowercase bare concept codes are rejected (invalid PascalCase)."""
        with pytest.raises(ValidationError, match="must be a valid concept ref"):
            ConceptBlueprint(
                description="A concept with invalid refines",
                refines="somecustomconcept",
            )

    def test_refines_empty_string_rejected(self):
        """Test that empty string refines is rejected as invalid."""
        with pytest.raises(ValidationError, match="must be a valid concept ref"):
            ConceptBlueprint(
                description="A concept with empty refines",
                refines="",
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

    def test_refines_non_native_with_underscore_domain(self):
        """Test refines with underscore domain names (valid snake_case)."""
        blueprint = ConceptBlueprint(
            description="Refines from domain with underscore",
            refines="my_app.Entity",
        )
        assert blueprint.refines == "my_app.Entity"

    def test_refines_hyphenated_domain_rejected(self):
        """Test that hyphenated domain names are rejected (not valid snake_case)."""
        with pytest.raises(ValidationError, match="must be a valid concept ref"):
            ConceptBlueprint(
                description="Refines from domain with hyphen",
                refines="my-app.Entity",
            )
