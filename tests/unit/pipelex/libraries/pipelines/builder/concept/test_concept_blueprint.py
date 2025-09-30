import pytest

from pipelex import log
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.libraries.pipelines.builder.concept.concept_spec import ConceptSpec

from tests.unit.pipelex.libraries.pipelines.builder.concept.test_data import ConceptBlueprintTestCases, ConceptCodeValidationTestCases


class TestConceptBlueprintConversion:
    @pytest.mark.parametrize(
        "topic,concept_spec,expected_core",
        ConceptBlueprintTestCases.TEST_CASES,
    )
    def test_concept_to_core_blueprint(self, topic: str, concept_spec: ConceptSpec, expected_core: ConceptBlueprint):
        log.verbose(f"Testing {topic}")
        result = concept_spec.to_blueprint()
        assert result == expected_core


class TestConceptCodeValidation:
    """Tests for concept code validation and snake_case to PascalCase conversion."""

    @pytest.mark.parametrize(
        "topic,input_code,expected_code",
        ConceptCodeValidationTestCases.TEST_CASES,
    )
    def test_concept_code_conversion(self, topic: str, input_code: str, expected_code: str):
        """Test that concept codes are properly converted from snake_case to PascalCase."""
        log.verbose(f"Testing {topic}: '{input_code}' -> '{expected_code}'")

        # Create a ConceptSpec with the input code
        concept_spec = ConceptSpec(
            the_concept_code=input_code,
            definition="Test concept for code validation",
            refines=None,
            structure=None,
        )

        # Verify the concept code was converted correctly
        assert concept_spec.the_concept_code == expected_code, (
            f"Expected concept code to be '{expected_code}', but got '{concept_spec.the_concept_code}'"
        )
