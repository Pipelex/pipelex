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

    def make_concept(self) -> Concept:
        code: str = self.value
        match self:
            case NativeConceptCode.TEXT:
                return Concept(
                    code=ConceptFactory.make_concept_code(SpecialDomain.NATIVE, code),
                    domain=SpecialDomain.NATIVE,
                    definition="A text",
                    structure_class_name=NativeConceptClass.TEXT,
                )
            case NativeConceptCode.IMAGE:
                return Concept(
                    code=ConceptFactory.make_concept_code(SpecialDomain.NATIVE, code),
                    domain=SpecialDomain.NATIVE,
                    definition="An image",
                    structure_class_name=NativeConceptClass.IMAGE,
                )
            case NativeConceptCode.PDF:
                return Concept(
                    code=ConceptFactory.make_concept_code(SpecialDomain.NATIVE, code),
                    domain=SpecialDomain.NATIVE,
                    definition="A PDF",
                    structure_class_name=NativeConceptClass.PDF,
                )
            case NativeConceptCode.TEXT_AND_IMAGES:
                return Concept(
                    code=ConceptFactory.make_concept_code(SpecialDomain.NATIVE, code),
                    domain=SpecialDomain.NATIVE,
                    definition="A text and an image",
                    structure_class_name=NativeConceptClass.TEXT_AND_IMAGES,
                )

            case NativeConceptCode.NUMBER:
                return Concept(
                    code=ConceptFactory.make_concept_code(SpecialDomain.NATIVE, code),
                    domain=SpecialDomain.NATIVE,
                    definition="A number",
                    structure_class_name=NativeConceptClass.NUMBER,
                )
            case NativeConceptCode.LLM_PROMPT:
                return Concept(
                    code=ConceptFactory.make_concept_code(SpecialDomain.NATIVE, code),
                    domain=SpecialDomain.NATIVE,
                    definition="A prompt for an LLM",
                    structure_class_name=NativeConceptClass.LLM_PROMPT,
                )
            case NativeConceptCode.DYNAMIC:
                return Concept(
                    code=ConceptFactory.make_concept_code(SpecialDomain.NATIVE, code),
                    domain=SpecialDomain.NATIVE,
                    definition="A dynamic concept",
                    structure_class_name=NativeConceptClass.DYNAMIC,
                )
            case NativeConceptCode.PAGE:
                return Concept(
                    code=ConceptFactory.make_concept_code(SpecialDomain.NATIVE, code),
                    domain=SpecialDomain.NATIVE,
                    definition="The content of a page of a document, comprising text and linked images as well as an optional screenshot of the page",
                    structure_class_name=NativeConceptClass.PAGE,
                )

    @classmethod
    def all_concepts(cls) -> List[Concept]:
        concepts: List[Concept] = []
        for code in cls:
            concepts.append(code.make_concept())
        return concepts
