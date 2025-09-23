import pytest

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.libraries.pipelines.builder.concept.concept_spec import ConceptSpec

from .test_data import ConceptBlueprintTestCases


class TestConceptBlueprintConversion:
    @pytest.mark.parametrize(
        "test_name,concept_spec,expected_core",
        ConceptBlueprintTestCases.TEST_CASES,
    )
    def test_concept_to_core_blueprint(self, test_name: str, concept_spec: ConceptSpec, expected_core: ConceptBlueprint):
        result = concept_spec.to_blueprint()
        assert result == expected_core
