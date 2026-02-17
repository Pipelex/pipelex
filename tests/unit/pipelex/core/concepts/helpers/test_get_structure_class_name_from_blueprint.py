"""Tests for get_structure_class_name_from_blueprint function."""

import pytest

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.helpers import get_structure_class_name_from_blueprint


class TestGetStructureClassNameFromBlueprint:
    """Test get_structure_class_name_from_blueprint function."""

    def test_string_blueprint_returns_concept_code(self):
        """When blueprint is a string description, returns the concept code."""
        result = get_structure_class_name_from_blueprint(
            blueprint_or_string_description="A simple description",
            concept_ref_or_code="MyConceptName",
        )
        assert result == "MyConceptName"

    def test_string_blueprint_with_concept_ref_returns_concept_code(self):
        """When blueprint is a string and input is a concept ref, extracts and returns concept code."""
        result = get_structure_class_name_from_blueprint(
            blueprint_or_string_description="A simple description",
            concept_ref_or_code="domain.MyConceptName",
        )
        assert result == "MyConceptName"

    def test_blueprint_with_string_structure_returns_structure_value(self):
        """When blueprint.structure is a string, returns that string as the class name."""
        blueprint = ConceptBlueprint(
            description="A concept with string structure",
            structure="CustomClassName",
        )
        result = get_structure_class_name_from_blueprint(
            blueprint_or_string_description=blueprint,
            concept_ref_or_code="MyConceptName",
        )
        assert result == "CustomClassName"

    def test_blueprint_with_dict_structure_returns_concept_code(self):
        """When blueprint.structure is a dict, returns the concept code."""
        blueprint = ConceptBlueprint(
            description="A concept with dict structure",
            structure={
                "field1": "Description of field1",
            },
        )
        result = get_structure_class_name_from_blueprint(
            blueprint_or_string_description=blueprint,
            concept_ref_or_code="MyConceptName",
        )
        assert result == "MyConceptName"

    def test_blueprint_with_none_structure_returns_concept_code(self):
        """When blueprint.structure is None, returns the concept code."""
        blueprint = ConceptBlueprint(
            description="A concept without structure",
            structure=None,
        )
        result = get_structure_class_name_from_blueprint(
            blueprint_or_string_description=blueprint,
            concept_ref_or_code="MyConceptName",
        )
        assert result == "MyConceptName"

    def test_blueprint_with_refines_and_no_structure_returns_concept_code(self):
        """When blueprint has refines but no structure, returns the concept code."""
        blueprint = ConceptBlueprint(
            description="A concept that refines another",
            refines="Text",
        )
        result = get_structure_class_name_from_blueprint(
            blueprint_or_string_description=blueprint,
            concept_ref_or_code="RefinedText",
        )
        assert result == "RefinedText"

    def test_concept_ref_with_underscore_domain_extracts_code(self):
        """Concept ref with underscore domain correctly extracts concept code."""
        result = get_structure_class_name_from_blueprint(
            blueprint_or_string_description="A description",
            concept_ref_or_code="my_domain.MyConceptName",
        )
        assert result == "MyConceptName"

    def test_invalid_concept_ref_or_code_raises_error(self):
        """Invalid concept_ref_or_code raises ValueError."""
        with pytest.raises(ValueError, match="Invalid concept_ref_or_code"):
            get_structure_class_name_from_blueprint(
                blueprint_or_string_description="A description",
                concept_ref_or_code="invalid_lowercase_code",
            )

    def test_hierarchical_domain_extracts_concept_code(self):
        """Hierarchical domain format (multiple dots) extracts the concept code correctly."""
        result = get_structure_class_name_from_blueprint(
            blueprint_or_string_description="A description",
            concept_ref_or_code="domain.subdomain.ConceptName",
        )
        assert result == "ConceptName"

    def test_empty_string_raises_error(self):
        """Empty string raises ValueError."""
        with pytest.raises(ValueError, match="Invalid concept_ref_or_code"):
            get_structure_class_name_from_blueprint(
                blueprint_or_string_description="A description",
                concept_ref_or_code="",
            )
