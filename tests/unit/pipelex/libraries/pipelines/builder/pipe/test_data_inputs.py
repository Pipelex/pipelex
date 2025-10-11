from typing import ClassVar

from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint


class InputRequirementTestCases:
    SIMPLE_TEXT_INPUT = (
        "simple_text_input",
        "Text",
        InputRequirementBlueprint(concept="Text"),
    )

    IMAGE_INPUT = (
        "image_input",
        "Image",
        InputRequirementBlueprint(concept="Image"),
    )

    CUSTOM_CONCEPT_INPUT = (
        "custom_concept_input",
        "CustomConcept",
        InputRequirementBlueprint(concept="CustomConcept"),
    )

    DOMAIN_CONCEPT_INPUT = (
        "domain_concept_input",
        "domain.ConceptName",
        InputRequirementBlueprint(concept="domain.ConceptName"),
    )

    TEST_CASES: ClassVar[list[tuple[str, str, InputRequirementBlueprint]]] = [
        SIMPLE_TEXT_INPUT,
        IMAGE_INPUT,
        CUSTOM_CONCEPT_INPUT,
        DOMAIN_CONCEPT_INPUT,
    ]
