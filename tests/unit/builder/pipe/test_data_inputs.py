from typing import ClassVar


class InputRequirementTestCases:
    SIMPLE_TEXT_INPUT = (
        "simple_text_input",
        "Text",
        "Text",
    )

    IMAGE_INPUT = (
        "image_input",
        "Image",
        "Image",
    )

    CUSTOM_CONCEPT_INPUT = (
        "custom_concept_input",
        "CustomConcept",
        "CustomConcept",
    )

    DOMAIN_CONCEPT_INPUT = (
        "domain_concept_input",
        "domain.ConceptName",
        "domain.ConceptName",
    )

    TEST_CASES: ClassVar[list[tuple[str, str, str]]] = [
        SIMPLE_TEXT_INPUT,
        IMAGE_INPUT,
        CUSTOM_CONCEPT_INPUT,
        DOMAIN_CONCEPT_INPUT,
    ]
