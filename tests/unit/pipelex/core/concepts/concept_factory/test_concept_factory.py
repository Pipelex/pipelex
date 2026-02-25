import pytest

from pipelex import pretty_print
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import (
    ConceptBlueprint,
    ConceptStructureBlueprint,
)
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprintFieldType
from pipelex.core.concepts.exceptions import ConceptFactoryError
from pipelex.core.concepts.helpers import normalize_structure_blueprint
from tests.unit.pipelex.core.concepts.concept_factory.data import TestCases


class TestConceptFactory:
    """Test ConceptFactory methods with various configurations."""

    @pytest.mark.parametrize(
        ("test_name", "domain_code", "blueprint", "expected_result"),
        TestCases.MAKE_REFINES_TEST_CASES,
    )
    def test_make_refine(
        self,
        test_name: str,
        domain_code: str,
        blueprint: ConceptBlueprint,
        expected_result: str,
    ):
        """Test make_refines method with different blueprint configurations."""
        if not blueprint.refines:
            pytest.skip("Test case has no refines")
        result = ConceptFactory.make_refine(refine=blueprint.refines, domain_code=domain_code)
        assert result == expected_result, f"Failed for test case: {test_name}"

    def test_normalize_structure_blueprint(self):
        """Test that mixed structure blueprints are properly normalized."""
        mixed_structure_blueprint: dict[str, str | ConceptStructureBlueprint] = {
            "name": "The name of the person",
            "age": ConceptStructureBlueprint(description="The age of the person", type=ConceptStructureBlueprintFieldType.NUMBER, required=True),
            "active": ConceptStructureBlueprint(
                description="Whether the person is active",
                type=ConceptStructureBlueprintFieldType.BOOLEAN,
                required=False,
                default_value=True,
            ),
        }

        expected_structure: dict[str, ConceptStructureBlueprint] = {
            "name": ConceptStructureBlueprint(description="The name of the person", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
            "age": ConceptStructureBlueprint(description="The age of the person", type=ConceptStructureBlueprintFieldType.NUMBER, required=True),
            "active": ConceptStructureBlueprint(
                description="Whether the person is active",
                type=ConceptStructureBlueprintFieldType.BOOLEAN,
                required=False,
                default_value=True,
            ),
        }

        assert normalize_structure_blueprint(mixed_structure_blueprint) == expected_structure

        mixed_structure_blueprint2: dict[str, str | ConceptStructureBlueprint] = {
            "name": ConceptStructureBlueprint(description="The name of the person", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
            "age": ConceptStructureBlueprint(description="The age of the person", type=ConceptStructureBlueprintFieldType.NUMBER, required=True),
            "active": ConceptStructureBlueprint(
                description="Whether the person is active",
                type=ConceptStructureBlueprintFieldType.BOOLEAN,
                required=False,
                default_value=True,
            ),
        }

        expected_structure2: dict[str, ConceptStructureBlueprint] = {
            "name": ConceptStructureBlueprint(description="The name of the person", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
            "age": ConceptStructureBlueprint(description="The age of the person", type=ConceptStructureBlueprintFieldType.NUMBER, required=True),
            "active": ConceptStructureBlueprint(
                description="Whether the person is active",
                type=ConceptStructureBlueprintFieldType.BOOLEAN,
                required=False,
                default_value=True,
            ),
        }

        assert normalize_structure_blueprint(mixed_structure_blueprint2) == expected_structure2

    @pytest.mark.parametrize(
        ("domain_code", "concept_ref_or_code", "expected_result"),
        TestCases.MAKE_DOMAIN_AND_CONCEPT_CODE_TEST_CASES,
    )
    def test_make_domain_and_concept_code_from_concept_ref_or_code(
        self,
        domain_code: str,
        concept_ref_or_code: str,
        expected_result: list[str],
    ):
        result = ConceptFactory.make_domain_and_concept_code_from_concept_ref_or_code(
            domain_code=domain_code,
            concept_ref_or_code=concept_ref_or_code,
        )
        assert result == expected_result

    @pytest.mark.parametrize(
        ("test_name", "domain_code", "concept_code", "blueprint", "expected_concept"),
        TestCases.MAKE_FROM_BLUEPRINT_TEST_CASES,
    )
    def test_make_from_blueprint(
        self,
        test_name: str,
        domain_code: str,
        concept_code: str,
        blueprint: ConceptBlueprint,
        expected_concept: Concept,
    ):
        """Test make_from_blueprint method with various blueprint configurations."""
        result = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code=concept_code,
            blueprint_or_string_description=blueprint,
        )
        pretty_print(result)
        pretty_print(expected_concept)

        assert result == expected_concept, f"Concept mismatch for {test_name}"

    def test_make_from_blueprint_with_invalid_structure_class(self):
        """Test that make_from_blueprint raises StructureClassError for invalid structure class."""
        blueprint = ConceptBlueprint(description="A concept with invalid structure", structure="NonExistentStructureClass")

        with pytest.raises(ConceptFactoryError, match="is not a registered subclass of StuffContent"):
            ConceptFactory.make_from_blueprint(
                domain_code="my_domain",
                concept_code="TestConcept",
                blueprint_or_string_description=blueprint,
            )
