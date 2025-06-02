from enum import Enum
from typing import List

from pipelex.core.concept import Concept
from pipelex.core.concept_factory import ConceptFactory
from pipelex.core.domain import SpecialDomain
from pipelex.types import StrEnum


class NativeConceptClass(StrEnum):
    DYNAMIC = "DynamicContent"
    TEXT = "TextContent"
    IMAGE = "ImageContent"
    PDF = "PDFContent"
    TEXT_AND_IMAGES = "TextAndImagesContent"
    NUMBER = "NumberContent"
    LLM_PROMPT = "LLMPromptContent"
    PAGE = "PageContent"


# Exceptionally, we use an Enum here (and not our usual StrEnum) to avoid confusion with
# the concept_code with must have the form "native.ConceptName"
class NativeConcept(Enum):
    DYNAMIC = "Dynamic"
    TEXT = "Text"
    IMAGE = "Image"
    PDF = "PDF"
    TEXT_AND_IMAGES = "TextAndImages"
    NUMBER = "Number"
    LLM_PROMPT = "LlmPrompt"
    PAGE = "Page"

    @classmethod
    def names(cls) -> List[str]:
        return [code.value for code in cls]

    @property
    def code(self) -> str:
        return ConceptFactory.make_concept_code(SpecialDomain.NATIVE, self.value)

    @property
    def content_class_name(self) -> NativeConceptClass:
        match self:
            case NativeConcept.TEXT:
                return NativeConceptClass.TEXT
            case NativeConcept.IMAGE:
                return NativeConceptClass.IMAGE
            case NativeConcept.PDF:
                return NativeConceptClass.PDF
            case NativeConcept.TEXT_AND_IMAGES:
                return NativeConceptClass.TEXT_AND_IMAGES
            case NativeConcept.NUMBER:
                return NativeConceptClass.NUMBER
            case NativeConcept.LLM_PROMPT:
                return NativeConceptClass.LLM_PROMPT
            case NativeConcept.DYNAMIC:
                return NativeConceptClass.DYNAMIC
            case NativeConcept.PAGE:
                return NativeConceptClass.PAGE

    def make_concept(self) -> Concept:
        definition: str
        match self:
            case NativeConcept.TEXT:
                definition = "A text"
            case NativeConcept.IMAGE:
                definition = "An image"
            case NativeConcept.PDF:
                definition = "A PDF"
            case NativeConcept.TEXT_AND_IMAGES:
                definition = "A text and an image"
            case NativeConcept.NUMBER:
                definition = "A number"
            case NativeConcept.LLM_PROMPT:
                definition = "A prompt for an LLM"
            case NativeConcept.DYNAMIC:
                definition = "A dynamic concept"
            case NativeConcept.PAGE:
                definition = "The content of a page of a document, comprising text and linked images as well as an optional page view image"

        return Concept(
            code=self.code,
            domain=SpecialDomain.NATIVE,
            definition=definition,
            structure_class_name=self.content_class_name,
        )

    @classmethod
    def all_concepts(cls) -> List[Concept]:
        concepts: List[Concept] = []
        for code in cls:
            concepts.append(code.make_concept())
        return concepts
