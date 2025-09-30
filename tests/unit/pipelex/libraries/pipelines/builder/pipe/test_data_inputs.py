from typing import ClassVar

from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint



class InputRequirementTestCases:
    SIMPLE_TEXT_INPUT = (
        "simple_text_input",
        "Text",
        "test_domain",
        InputRequirementBlueprint(concept="Text"),
    )

    IMAGE_INPUT = (
        "image_input",
        "Image",
        "test_domain",
        InputRequirementBlueprint(concept="Image"),
    )

    CUSTOM_CONCEPT_INPUT = (
        "custom_concept_input",
        "CustomConcept",
        "test_domain",
        InputRequirementBlueprint(concept="CustomConcept"),
    )

    DOMAIN_CONCEPT_INPUT = (
        "domain_concept_input",
        "domain.ConceptName",
        "test_domain",
        InputRequirementBlueprint(concept="domain.ConceptName"),
    )

    TEST_CASES: ClassVar[list[tuple[str, str, str, InputRequirementBlueprint]]] = [
        SIMPLE_TEXT_INPUT,
        IMAGE_INPUT,
        CUSTOM_CONCEPT_INPUT,
        DOMAIN_CONCEPT_INPUT,
    ]
