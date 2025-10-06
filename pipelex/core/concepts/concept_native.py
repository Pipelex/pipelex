from pipelex.core.domains.domain import SpecialDomain
from pipelex.types import StrEnum


class NativeConceptEnumError(Exception):
    pass


class NativeConceptCode(StrEnum):
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
    def concept_string(self) -> str:
        return f"{SpecialDomain.NATIVE}.{self.value}"

    @property
    def structure_class_name(self) -> str:
        return f"{self.value}Content"

    @classmethod
    def is_text(cls, concept_code: str) -> bool:
        try:
            enum_value = NativeConceptCode(concept_code)
        except ValueError:
            return False

        match enum_value:
            case NativeConceptCode.TEXT:
                return True
            case (
                NativeConceptCode.DYNAMIC
                | NativeConceptCode.IMAGE
                | NativeConceptCode.PDF
                | NativeConceptCode.TEXT_AND_IMAGES
                | NativeConceptCode.NUMBER
                | NativeConceptCode.LLM_PROMPT
                | NativeConceptCode.PAGE
                | NativeConceptCode.ANYTHING
            ):
                return False

    @classmethod
    def values_list(cls) -> list["NativeConceptCode"]:
        return list(cls)

    @classmethod
    def is_native_concept(cls, concept_code: str) -> bool:
        return concept_code in cls.values_list()

    @classmethod
    def native_concept_class_names(cls):
        return [native_concept.structure_class_name for native_concept in cls]

    @classmethod
    def get_validated_native_concept_string(cls, concept_string_or_code: str) -> str | None:
        if "." in concept_string_or_code:
            if concept_string_or_code.count(".") > 1:
                msg = f"Trying to get a native concept with code '{concept_string_or_code}' but that is not a native concept"
                raise NativeConceptEnumError(msg)
            domain_code, concept_code = concept_string_or_code.split(".", 1)
            if SpecialDomain.is_native(domain=domain_code) and concept_code in cls.values_list():
                return concept_string_or_code
            else:
                return None
        elif concept_string_or_code in cls.values_list():
            return f"{SpecialDomain.NATIVE}.{concept_string_or_code}"
        else:
            return None


# class NativeConceptManager:
# @classmethod
# def is_native_concept(cls, concept_string_or_code: str) -> bool:
#     native_concept_values = NativeConceptCode.values_list()

#     if "." in concept_string_or_code:
#         domain, concept_code = concept_string_or_code.split(".", 1)
#         if SpecialDomain.is_native(domain=domain) and concept_code in native_concept_values:
#             return True

#     return concept_string_or_code in native_concept_values

# @classmethod
# def get_native_concept_string(cls, concept_string_or_code: str) -> str:
#     if not cls.is_native_concept(concept_string_or_code):
#         msg = f"Trying to get a native concept with code '{concept_string_or_code}' that is not a native concept"
#         raise NativeConceptEnumError(msg)

#     if "." in concept_string_or_code and SpecialDomain.is_native(domain=concept_string_or_code.split(".")[0]):
#         return concept_string_or_code

#     return f"{SpecialDomain.NATIVE}.{concept_string_or_code}"

# @classmethod
# def get_native_concept_enum(cls, concept_string_or_code: str) -> NativeConceptCode:
#     if not cls.is_native_concept(concept_string_or_code):
#         msg = f"Trying to get a native concept with string or code '{concept_string_or_code}' that is not a native concept"
#         raise NativeConceptEnumError(msg)

#     if "." in concept_string_or_code:
#         _, concept_code = concept_string_or_code.split(".", 1)
#     else:
#         concept_code = concept_string_or_code

#     return NativeConceptCode(concept_code)
