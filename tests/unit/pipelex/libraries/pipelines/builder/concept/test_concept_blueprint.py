"""
Test suite for ConceptBlueprint.to_core_blueprint conversion method.
"""

import pytest

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.libraries.pipelines.builder.concept.concept_spec import ConceptSpec

from .test_data import ConceptBlueprintTestCases


class TestConceptBlueprintConversion:
    """Test ConceptBlueprint.to_core_blueprint conversion."""

    @pytest.mark.parametrize(
        "test_name,concept_blueprint,expected_core",
        ConceptBlueprintTestCases.TEST_CASES,
    )
    def test_concept_to_core_blueprint(self, test_name: str, concept_blueprint: ConceptSpec, expected_core: ConceptBlueprint):
        """Test converting various concept blueprints to core blueprints."""
        result = concept_blueprint.to_core_blueprint()
        assert result == expected_core
