# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from enum import StrEnum
from typing import List

from pipelex.core.concept import Concept
from pipelex.core.concept_factory import ConceptFactory
from pipelex.core.domain import SpecialDomain


class NativeConceptClass(StrEnum):
    DYNAMIC = "DynamicContent"
    TEXT = "TextContent"
    IMAGE = "ImageContent"
    PDF = "PDFContent"
    TEXT_AND_IMAGES = "TextAndImagesContent"
    NUMBER = "NumberContent"
    LLM_PROMPT = "LLMPromptContent"
    PAGE = "PageContent"


class NativeConceptCode(StrEnum):
    DYNAMIC = "Dynamic"
    TEXT = "Text"
    IMAGE = "Image"
    PDF = "PDF"
    TEXT_AND_IMAGES = "TextAndImage"
    NUMBER = "Number"
    LLM_PROMPT = "LlmPrompt"
    PAGE = "Page"

    @property
    def concept_code(self) -> str:
        return ConceptFactory.make_concept_code(SpecialDomain.NATIVE, self.value)

    @property
    def content_class_name(self) -> NativeConceptClass:
        match self:
            case NativeConceptCode.TEXT:
                return NativeConceptClass.TEXT
            case NativeConceptCode.IMAGE:
                return NativeConceptClass.IMAGE
            case NativeConceptCode.PDF:
                return NativeConceptClass.PDF
            case NativeConceptCode.TEXT_AND_IMAGES:
                return NativeConceptClass.TEXT_AND_IMAGES
            case NativeConceptCode.NUMBER:
                return NativeConceptClass.NUMBER
            case NativeConceptCode.LLM_PROMPT:
                return NativeConceptClass.LLM_PROMPT
            case NativeConceptCode.DYNAMIC:
                return NativeConceptClass.DYNAMIC
            case NativeConceptCode.PAGE:
                return NativeConceptClass.PAGE

    def make_concept(self) -> Concept:
        definition: str
        match self:
            case NativeConceptCode.TEXT:
                definition = "A text"
            case NativeConceptCode.IMAGE:
                definition = "An image"
            case NativeConceptCode.PDF:
                definition = "A PDF"
            case NativeConceptCode.TEXT_AND_IMAGES:
                definition = "A text and an image"
            case NativeConceptCode.NUMBER:
                definition = "A number"
            case NativeConceptCode.LLM_PROMPT:
                definition = "A prompt for an LLM"
            case NativeConceptCode.DYNAMIC:
                definition = "A dynamic concept"
            case NativeConceptCode.PAGE:
                definition = "The content of a page of a document, comprising text and linked images as well as an optional screenshot of the page"

        return Concept(
            code=ConceptFactory.make_concept_code(SpecialDomain.NATIVE, self),
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
