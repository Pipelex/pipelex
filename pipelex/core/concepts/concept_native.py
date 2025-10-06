from pipelex.core.domains.domain import SpecialDomain
from pipelex.types import StrEnum


class NativeConceptEnumError(Exception):
    pass


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

    @property
    def structure_class_name(self) -> str:
        return f"{self.value}Content"

    @classmethod
    def values_list(cls) -> list["NativeConceptEnum"]:
        return list(cls)

    @classmethod
    def is_native_concept(cls, concept_code: str) -> bool:
        return concept_code in cls.values_list()

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

    @classmethod
    def native_concept_class_names(cls):
        return [native_concept.structure_class_name for native_concept in cls]


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
