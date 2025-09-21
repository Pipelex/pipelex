"""
Test data for InputRequirementBlueprint conversion tests.
"""

from typing import ClassVar, List, Tuple

from pipelex.core.pipes.pipe_input_spec_blueprint import (
    InputRequirementBlueprint as InputRequirementBlueprintCore,
)
from pipelex.libraries.pipelines.builder.pipe.inputs import InputRequirementBlueprint


class InputRequirementTestCases:
    """Test cases for InputRequirementBlueprint conversion."""

    SIMPLE_TEXT_INPUT = (
        "simple_text_input",
        InputRequirementBlueprint(concept="Text"),
        "test_domain",
        InputRequirementBlueprintCore(concept="Text"),
    )

    IMAGE_INPUT = (
        "image_input",
        InputRequirementBlueprint(concept="Image"),
        "test_domain",
        InputRequirementBlueprintCore(concept="Image"),
    )

    CUSTOM_CONCEPT_INPUT = (
        "custom_concept_input",
        InputRequirementBlueprint(concept="CustomConcept"),
        "test_domain",
        InputRequirementBlueprintCore(concept="CustomConcept"),
    )

    DOMAIN_CONCEPT_INPUT = (
        "domain_concept_input",
        InputRequirementBlueprint(concept="domain.ConceptName"),
        "test_domain",
        InputRequirementBlueprintCore(concept="domain.ConceptName"),
    )

    TEST_CASES: ClassVar[List[Tuple[str, InputRequirementBlueprint, str, InputRequirementBlueprintCore]]] = [
        SIMPLE_TEXT_INPUT,
        IMAGE_INPUT,
        CUSTOM_CONCEPT_INPUT,
        DOMAIN_CONCEPT_INPUT,
    ]
