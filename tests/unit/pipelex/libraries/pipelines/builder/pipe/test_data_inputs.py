from typing import ClassVar

from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.inputs_spec import InputRequirementSpec


class InputRequirementTestCases:
    SIMPLE_TEXT_INPUT = (
        "simple_text_input",
        InputRequirementSpec(concept="Text"),
        "test_domain",
        InputRequirementBlueprint(concept="Text"),
    )

    IMAGE_INPUT = (
        "image_input",
        InputRequirementSpec(concept="Image"),
        "test_domain",
        InputRequirementBlueprint(concept="Image"),
    )

    CUSTOM_CONCEPT_INPUT = (
        "custom_concept_input",
        InputRequirementSpec(concept="CustomConcept"),
        "test_domain",
        InputRequirementBlueprint(concept="CustomConcept"),
    )

    DOMAIN_CONCEPT_INPUT = (
        "domain_concept_input",
        InputRequirementSpec(concept="domain.ConceptName"),
        "test_domain",
        InputRequirementBlueprint(concept="domain.ConceptName"),
    )

    TEST_CASES: ClassVar[list[tuple[str, InputRequirementSpec, str, InputRequirementBlueprint]]] = [
        SIMPLE_TEXT_INPUT,
        IMAGE_INPUT,
        CUSTOM_CONCEPT_INPUT,
        DOMAIN_CONCEPT_INPUT,
    ]
