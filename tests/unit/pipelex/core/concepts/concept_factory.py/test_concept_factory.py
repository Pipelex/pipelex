"""Tests for ConceptFactory methods."""

from typing import Dict, List, Optional

import pytest

from pipelex.core.concepts.concept_blueprint import (
    ConceptBlueprint,
    ConceptStructureBlueprint,
    ConceptStructureBlueprintFieldType,
    ConceptStructureBlueprintType,
)
from pipelex.core.concepts.concept_factory import ConceptFactory

from .data import TestCases


class TestConceptFactory:
    """Test ConceptFactory._make_refines method with various refines configurations."""

    @pytest.mark.parametrize(
        "test_name,blueprint,expected_result",
        TestCases.TEST_CASES,
    )
    def test_make_refines(
        self,
        test_name: str,
        blueprint: ConceptBlueprint,
        expected_result: List[str],
    ):
        """Test _make_refines method with different blueprint configurations."""
        result = ConceptFactory.make_refines(blueprint=blueprint)
        assert result == expected_result, f"Failed for test case: {test_name}"

    def test_normalize_structure_blueprint(self):
        """Test that mixed structure blueprints are properly normalized."""
        mixed_structure_blueprint: Dict[str, ConceptStructureBlueprintType] = {
            "name": "The name of the person",
            "age": ConceptStructureBlueprint(definition="The age of the person", type=ConceptStructureBlueprintFieldType.NUMBER, required=True),
            "active": ConceptStructureBlueprint(
                definition="Whether the person is active", type=ConceptStructureBlueprintFieldType.BOOLEAN, required=False, default_value=True
            ),
        }

        expected_structure: Dict[str, ConceptStructureBlueprint] = {
            "name": ConceptStructureBlueprint(definition="The name of the person", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
            "age": ConceptStructureBlueprint(definition="The age of the person", type=ConceptStructureBlueprintFieldType.NUMBER, required=True),
            "active": ConceptStructureBlueprint(
                definition="Whether the person is active", type=ConceptStructureBlueprintFieldType.BOOLEAN, required=False, default_value=True
            ),
        }

        assert ConceptFactory.normalize_structure_blueprint(mixed_structure_blueprint) == expected_structure

        mixed_structure_blueprint2: Dict[str, ConceptStructureBlueprintType] = {
            "name": ConceptStructureBlueprint(definition="The name of the person", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
            "age": ConceptStructureBlueprint(definition="The age of the person", type=ConceptStructureBlueprintFieldType.NUMBER, required=True),
            "active": ConceptStructureBlueprint(
                definition="Whether the person is active", type=ConceptStructureBlueprintFieldType.BOOLEAN, required=False, default_value=True
            ),
        }

        expected_structure2: Dict[str, ConceptStructureBlueprint] = {
            "name": ConceptStructureBlueprint(definition="The name of the person", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
            "age": ConceptStructureBlueprint(definition="The age of the person", type=ConceptStructureBlueprintFieldType.NUMBER, required=True),
            "active": ConceptStructureBlueprint(
                definition="Whether the person is active", type=ConceptStructureBlueprintFieldType.BOOLEAN, required=False, default_value=True
            ),
        }

        assert ConceptFactory.normalize_structure_blueprint(mixed_structure_blueprint2) == expected_structure2

    @pytest.mark.parametrize(
        "domain,concept_string_or_concept_code,concept_codes_from_the_same_domain,expected_result",
        [
            # Test case 1: Concept string with dot notation
            ("my_domain", "other_domain.ConceptName", None, ["other_domain", "ConceptName"]),
            # Test case 2: Concept string with dot notation (ignores same domain codes)
            ("my_domain", "other_domain.ConceptName", ["ConceptName"], ["other_domain", "ConceptName"]),
            # Test case 3: Native concept code (Text)
            ("my_domain", "Text", None, ["native", "Text"]),
            # Test case 4: Native concept code (Image)
            ("my_domain", "Image", None, ["native", "Image"]),
            # Test case 5: Native concept code (PDF)
            ("my_domain", "PDF", None, ["native", "PDF"]),
            # Test case 6: Native concept code with same domain codes provided (native takes precedence)
            ("my_domain", "Text", ["Text", "OtherConcept"], ["native", "Text"]),
            # Test case 7: Concept code from same domain
            ("my_domain", "MyConcept", ["MyConcept", "OtherConcept"], ["my_domain", "MyConcept"]),
            # Test case 8: Concept code from same domain (case sensitive)
            ("my_domain", "MyConcept", ["MyCon", "OtherConcept"], ["implicit", "MyConcept"]),
            # Test case 9: Unknown concept code (no same domain codes)
            ("my_domain", "UnknownConcept", None, ["implicit", "UnknownConcept"]),
            # Test case 10: Unknown concept code (not in same domain codes)
            ("my_domain", "UnknownConcept", ["KnownConcept", "OtherConcept"], ["implicit", "UnknownConcept"]),
            # Test case 11: Empty same domain codes list
            ("my_domain", "SomeConcept", [], ["implicit", "SomeConcept"]),
            # Test case 12: Different domain in concept string
            ("my_domain", "another_domain.SomeConcept", ["SomeConcept"], ["another_domain", "SomeConcept"]),
            # Test case 13: All native concept codes
            ("my_domain", "Dynamic", None, ["native", "Dynamic"]),
            ("my_domain", "TextAndImages", None, ["native", "TextAndImages"]),
            ("my_domain", "Number", None, ["native", "Number"]),
            ("my_domain", "LlmPrompt", None, ["native", "LlmPrompt"]),
            ("my_domain", "Page", None, ["native", "Page"]),
            ("my_domain", "Anything", None, ["native", "Anything"]),
        ],
    )
    def test_make_domain_and_concept_code_from_concept_string_or_concept_code(
        self,
        domain: str,
        concept_string_or_concept_code: str,
        concept_codes_from_the_same_domain: Optional[List[str]],
        expected_result: List[str],
    ):
        """Test make_domain_and_concept_code_from_concept_string_or_concept_code method with various inputs."""
        result = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_concept_code(
            domain=domain,
            concept_string_or_concept_code=concept_string_or_concept_code,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )
        assert result == expected_result
