from typing import Dict, List, NamedTuple

from pipelex.core.domains.domain import SpecialDomain
from pipelex.types import StrEnum


class NativeConceptData(NamedTuple):
    code: str
    content_class_name: str
    definition: str


class NativeConcept(StrEnum):
    DYNAMIC = "Dynamic"
    TEXT = "Text"
    IMAGE = "Image"
    PDF = "PDF"
    TEXT_AND_IMAGES = "TextAndImages"
    NUMBER = "Number"
    LLM_PROMPT = "LlmPrompt"
    PAGE = "Page"


NATIVE_CONCEPTS_DATA: Dict[NativeConcept, NativeConceptData] = {
    NativeConcept.DYNAMIC: NativeConceptData(
        code=NativeConcept.DYNAMIC, content_class_name=f"{NativeConcept.DYNAMIC}Content", definition="A dynamic concept"
    ),
    NativeConcept.TEXT: NativeConceptData(code=NativeConcept.TEXT, content_class_name=f"{NativeConcept.TEXT}Content", definition="A text"),
    NativeConcept.IMAGE: NativeConceptData(code=NativeConcept.IMAGE, content_class_name=f"{NativeConcept.IMAGE}Content", definition="An image"),
    NativeConcept.PDF: NativeConceptData(code=NativeConcept.PDF, content_class_name=f"{NativeConcept.PDF}Content", definition="A PDF"),
    NativeConcept.TEXT_AND_IMAGES: NativeConceptData(
        code=NativeConcept.TEXT_AND_IMAGES, content_class_name=f"{NativeConcept.TEXT_AND_IMAGES}Content", definition="A text and an image"
    ),
    NativeConcept.NUMBER: NativeConceptData(code=NativeConcept.NUMBER, content_class_name=f"{NativeConcept.NUMBER}Content", definition="A number"),
    NativeConcept.LLM_PROMPT: NativeConceptData(
        code=NativeConcept.LLM_PROMPT, content_class_name=f"{NativeConcept.LLM_PROMPT}Content", definition="A prompt for an LLM"
    ),
    NativeConcept.PAGE: NativeConceptData(
        code=NativeConcept.PAGE,
        content_class_name=f"{NativeConcept.PAGE}Content",
        definition="The content of a page of a document, comprising text and linked images and an optional page view image",
    ),
}
