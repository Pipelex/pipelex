import pytest
from typing import Optional, List

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import (
    ConceptBlueprint,
    ConceptStructureBlueprint,
    ConceptStructureBlueprintFieldType,
)
from pipelex.core.concepts.concept_factory import ConceptFactory

from .data import TestCases


class TestConceptFactory:
    """Test ConceptFactory methods with various configurations."""

    @pytest.mark.parametrize(
        "test_name,blueprint,expected_result",
        TestCases.MAKE_REFINES_TEST_CASES,
    )
    def test_make_refines(
        self,
        test_name: str,
        blueprint: ConceptBlueprint,
        expected_result: str,
    ):
        """Test make_refines method with different blueprint configurations."""
        result = ConceptFactory.make_refines(blueprint=blueprint)
        assert result == expected_result, f"Failed for test case: {test_name}"

    def test_normalize_structure_blueprint(self):
        """Test that mixed structure blueprints are properly normalized."""
        mixed_structure_blueprint: dict[str, str | ConceptStructureBlueprint] = {
            "name": "The name of the person",
            "age": ConceptStructureBlueprint(definition="The age of the person", type=ConceptStructureBlueprintFieldType.NUMBER, required=True),
            "active": ConceptStructureBlueprint(
                definition="Whether the person is active", type=ConceptStructureBlueprintFieldType.BOOLEAN, required=False, default_value=True,
            ),
        }

        expected_structure: dict[str, ConceptStructureBlueprint] = {
            "name": ConceptStructureBlueprint(definition="The name of the person", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
            "age": ConceptStructureBlueprint(definition="The age of the person", type=ConceptStructureBlueprintFieldType.NUMBER, required=True),
            "active": ConceptStructureBlueprint(
                definition="Whether the person is active", type=ConceptStructureBlueprintFieldType.BOOLEAN, required=False, default_value=True,
            ),
        }

        assert ConceptFactory.normalize_structure_blueprint(mixed_structure_blueprint) == expected_structure

        mixed_structure_blueprint2: dict[str, str | ConceptStructureBlueprint] = {
            "name": ConceptStructureBlueprint(definition="The name of the person", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
            "age": ConceptStructureBlueprint(definition="The age of the person", type=ConceptStructureBlueprintFieldType.NUMBER, required=True),
            "active": ConceptStructureBlueprint(
                definition="Whether the person is active", type=ConceptStructureBlueprintFieldType.BOOLEAN, required=False, default_value=True,
            ),
        }

        expected_structure2: dict[str, ConceptStructureBlueprint] = {
            "name": ConceptStructureBlueprint(definition="The name of the person", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
            "age": ConceptStructureBlueprint(definition="The age of the person", type=ConceptStructureBlueprintFieldType.NUMBER, required=True),
            "active": ConceptStructureBlueprint(
                definition="Whether the person is active", type=ConceptStructureBlueprintFieldType.BOOLEAN, required=False, default_value=True,
            ),
        }

        assert ConceptFactory.normalize_structure_blueprint(mixed_structure_blueprint2) == expected_structure2

    @pytest.mark.parametrize(
        "domain,concept_string_or_code,concept_codes_from_the_same_domain,expected_result",
        TestCases.MAKE_DOMAIN_AND_CONCEPT_CODE_TEST_CASES,
    )
    def test_make_domain_and_concept_code_from_concept_string_or_code(
        self,
        domain: str,
        concept_string_or_code: str,
        concept_codes_from_the_same_domain: List[str] | None,
        expected_result: List[str],
    ):
        """Test make_domain_and_concept_code_from_concept_string_or_code method with various inputs."""
        result = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_code(
            domain=domain,
            concept_string_or_code=concept_string_or_code,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )
        assert result == expected_result

    @pytest.mark.parametrize(
        "test_name,domain,concept_code,blueprint,concept_codes_from_the_same_domain,expected_concept",
        TestCases.MAKE_FROM_BLUEPRINT_TEST_CASES,
    )
    def test_make_from_blueprint(
        self,
        test_name: str,
        domain: str,
        concept_code: str,
        blueprint: ConceptBlueprint,
        concept_codes_from_the_same_domain: list[str] | None,
        expected_concept: Concept,
    ):
        """Test make_from_blueprint method with various blueprint configurations."""
        result = ConceptFactory.make_from_blueprint(
            domain=domain,
            concept_code=concept_code,
            blueprint=blueprint,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )

        assert result == expected_concept, f"Concept mismatch for {test_name}"

    def test_make_from_blueprint_with_invalid_structure_class(self):
        """Test that make_from_blueprint raises StructureClassError for invalid structure class."""
        blueprint = ConceptBlueprint(definition="A concept with invalid structure", structure="NonExistentStructureClass")

        from pipelex.exceptions import StructureClassError

        with pytest.raises(StructureClassError, match="is not a registered subclass of StuffContent"):
            ConceptFactory.make_from_blueprint(
                domain="my_domain",
                concept_code="TestConcept",
                blueprint=blueprint,
            )
