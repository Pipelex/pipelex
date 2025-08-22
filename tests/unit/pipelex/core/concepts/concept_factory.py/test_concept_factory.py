"""Tests for ConceptFactory methods."""

from typing import Dict, List

import pytest

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint, ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
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
        result = ConceptFactory.make_refines(domain="test_domain", blueprint=blueprint)
        assert result == expected_result, f"Failed for test case: {test_name}"

    def test_normalize_structure_blueprint(self):
        """Test that mixed structure blueprints are properly normalized."""
        mixed_structure_blueprint = {
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
