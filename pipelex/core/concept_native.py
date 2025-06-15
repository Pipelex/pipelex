from enum import Enum
from typing import List

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
# the concept_code which must have the form "native.ConceptName"
class NativeConcept(Enum):
    ANYTHING = "Anything"
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
        if "." in self.value:
            return self.value
        return f"{SpecialDomain.NATIVE}.{self.value}"

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
            case NativeConcept.ANYTHING:
                raise RuntimeError("NativeConcept.ANYTHING cannot be used as a content class name")
