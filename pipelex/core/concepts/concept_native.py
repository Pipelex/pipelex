from typing import NamedTuple

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

    @classmethod
    def values_list(cls) -> list["NativeConceptEnum"]:
        return list(cls)

    @classmethod
    def is_text(cls, concept_code: str) -> bool:
        try:
            enum_value = NativeConceptEnum(concept_code)
        except ValueError:
            return False

        match enum_value:
            case NativeConceptEnum.TEXT:
                return True
            case (
                NativeConceptEnum.DYNAMIC
                | NativeConceptEnum.IMAGE
                | NativeConceptEnum.PDF
                | NativeConceptEnum.TEXT_AND_IMAGES
                | NativeConceptEnum.NUMBER
                | NativeConceptEnum.LLM_PROMPT
                | NativeConceptEnum.PAGE
                | NativeConceptEnum.ANYTHING
            ):
                return False


NATIVE_CONCEPTS_DATA: dict[NativeConceptEnum, NativeConceptEnumData] = {
    NativeConceptEnum.DYNAMIC: NativeConceptEnumData(
        code=NativeConceptEnum.DYNAMIC,
        content_class_name=f"{NativeConceptEnum.DYNAMIC}Content",
        definition="A dynamic concept",
    ),
    NativeConceptEnum.TEXT: NativeConceptEnumData(
        code=NativeConceptEnum.TEXT,
        content_class_name=f"{NativeConceptEnum.TEXT}Content",
        definition="A text",
    ),
    NativeConceptEnum.IMAGE: NativeConceptEnumData(
        code=NativeConceptEnum.IMAGE,
        content_class_name=f"{NativeConceptEnum.IMAGE}Content",
        definition="An image",
    ),
    NativeConceptEnum.PDF: NativeConceptEnumData(
        code=NativeConceptEnum.PDF,
        content_class_name=f"{NativeConceptEnum.PDF}Content",
        definition="A PDF",
    ),
    NativeConceptEnum.TEXT_AND_IMAGES: NativeConceptEnumData(
        code=NativeConceptEnum.TEXT_AND_IMAGES,
        content_class_name=f"{NativeConceptEnum.TEXT_AND_IMAGES}Content",
        definition="A text and an image",
    ),
    NativeConceptEnum.NUMBER: NativeConceptEnumData(
        code=NativeConceptEnum.NUMBER,
        content_class_name=f"{NativeConceptEnum.NUMBER}Content",
        definition="A number",
    ),
    NativeConceptEnum.LLM_PROMPT: NativeConceptEnumData(
        code=NativeConceptEnum.LLM_PROMPT,
        content_class_name=f"{NativeConceptEnum.LLM_PROMPT}Content",
        definition="A prompt for an LLM",
    ),
    NativeConceptEnum.PAGE: NativeConceptEnumData(
        code=NativeConceptEnum.PAGE,
        content_class_name=f"{NativeConceptEnum.PAGE}Content",
        definition="The content of a page of a document, comprising text and linked images and an optional page view image",
    ),
    NativeConceptEnum.ANYTHING: NativeConceptEnumData(
        code=NativeConceptEnum.ANYTHING,
        content_class_name=f"{NativeConceptEnum.ANYTHING}Content",
        definition="Anything",
    ),
}


class NativeConceptManager:
    @classmethod
    def is_native_concept(cls, concept_string_or_code: str) -> bool:
        native_concept_values = NativeConceptEnum.values_list()

        if "." in concept_string_or_code:
            domain, concept_code = concept_string_or_code.split(".", 1)
            if SpecialDomain.is_native(domain=domain) and concept_code in native_concept_values:
                return True

        return concept_string_or_code in native_concept_values

    @classmethod
    def get_native_concept_string(cls, concept_string_or_code: str) -> str:
        if not cls.is_native_concept(concept_string_or_code):
            msg = f"Trying to get a native concept with code '{concept_string_or_code}' that is not a native concept"
            raise NativeConceptEnumError(msg)

        if "." in concept_string_or_code and SpecialDomain.is_native(domain=concept_string_or_code.split(".")[0]):
            return concept_string_or_code

        return f"{SpecialDomain.NATIVE}.{concept_string_or_code}"

    @classmethod
    def get_native_concept_enum(cls, concept_string_or_code: str) -> NativeConceptEnum:
        if not cls.is_native_concept(concept_string_or_code):
            msg = f"Trying to get a native concept with string or code '{concept_string_or_code}' that is not a native concept"
            raise NativeConceptEnumError(msg)

        if "." in concept_string_or_code:
            _, concept_code = concept_string_or_code.split(".", 1)
        else:
            concept_code = concept_string_or_code

        return NativeConceptEnum(concept_code)

    @classmethod
    def get_native_concept_data(cls, concept_string_or_code: str) -> NativeConceptEnumData:
        enum_value = cls.get_native_concept_enum(concept_string_or_code)
        return NATIVE_CONCEPTS_DATA[enum_value]
