from typing import Dict, NamedTuple

from pipelex.core.domains.domain import SpecialDomain
from pipelex.types import StrEnum


class NativeConceptEnumError(Exception):
    pass


class NativeConceptEnumData(NamedTuple):
    code: str
    content_class_name: str
    definition: str


class NativeConceptEnum(StrEnum):
    DYNAMIC = "Dynamic"
    TEXT = "Text"
    IMAGE = "Image"
    PDF = "PDF"
    TEXT_AND_IMAGES = "TextAndImages"
    NUMBER = "Number"
    LLM_PROMPT = "LlmPrompt"
    PAGE = "Page"
    ANYTHING = "Anything"


NATIVE_CONCEPTS_DATA: Dict[NativeConceptEnum, NativeConceptEnumData] = {
    NativeConceptEnum.DYNAMIC: NativeConceptEnumData(
        code=NativeConceptEnum.DYNAMIC, content_class_name=f"{NativeConceptEnum.DYNAMIC}Content", definition="A dynamic concept"
    ),
    NativeConceptEnum.TEXT: NativeConceptEnumData(
        code=NativeConceptEnum.TEXT, content_class_name=f"{NativeConceptEnum.TEXT}Content", definition="A text"
    ),
    NativeConceptEnum.IMAGE: NativeConceptEnumData(
        code=NativeConceptEnum.IMAGE, content_class_name=f"{NativeConceptEnum.IMAGE}Content", definition="An image"
    ),
    NativeConceptEnum.PDF: NativeConceptEnumData(
        code=NativeConceptEnum.PDF, content_class_name=f"{NativeConceptEnum.PDF}Content", definition="A PDF"
    ),
    NativeConceptEnum.TEXT_AND_IMAGES: NativeConceptEnumData(
        code=NativeConceptEnum.TEXT_AND_IMAGES, content_class_name=f"{NativeConceptEnum.TEXT_AND_IMAGES}Content", definition="A text and an image"
    ),
    NativeConceptEnum.NUMBER: NativeConceptEnumData(
        code=NativeConceptEnum.NUMBER, content_class_name=f"{NativeConceptEnum.NUMBER}Content", definition="A number"
    ),
    NativeConceptEnum.LLM_PROMPT: NativeConceptEnumData(
        code=NativeConceptEnum.LLM_PROMPT, content_class_name=f"{NativeConceptEnum.LLM_PROMPT}Content", definition="A prompt for an LLM"
    ),
    NativeConceptEnum.PAGE: NativeConceptEnumData(
        code=NativeConceptEnum.PAGE,
        content_class_name=f"{NativeConceptEnum.PAGE}Content",
        definition="The content of a page of a document, comprising text and linked images and an optional page view image",
    ),
    NativeConceptEnum.ANYTHING: NativeConceptEnumData(
        code=NativeConceptEnum.ANYTHING, content_class_name=f"{NativeConceptEnum.ANYTHING}Content", definition="Anything"
    ),
}


def is_native_concept(concept_string_or_concept_code: str) -> bool:
    """Check if a concept reference is a native concept (short or fully qualified form)."""
    native_concept_values = [native_concept.value for native_concept in NativeConceptEnum]

    # Check short form (e.g., "Text")
    if concept_string_or_concept_code in native_concept_values:
        return True

    # Check fully qualified form (e.g., "native.Text")
    if "." in concept_string_or_concept_code:
        domain, concept_code = concept_string_or_concept_code.split(".", 1)
        if domain == SpecialDomain.NATIVE.value and concept_code in native_concept_values:
            return True

    return False
