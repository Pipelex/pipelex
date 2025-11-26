from pipelex.core.concepts.native.exceptions import NativeConceptDefinitionError
from pipelex.core.concepts.validation import is_concept_string_or_code_valid
from pipelex.core.domains.domain import SpecialDomain
from pipelex.types import StrEnum


class NativeConceptCode(StrEnum):
    DYNAMIC = "Dynamic"
    TEXT = "Text"
    IMAGE = "Image"
    PDF = "PDF"
    TEXT_AND_IMAGES = "TextAndImages"
    NUMBER = "Number"
    IMG_GEN_PROMPT = "ImgGenPrompt"
    PAGE = "Page"
    JSON = "JSON"
    ANYTHING = "Anything"

    @property
    def as_output_multiple_indeterminate(self) -> str:
        return f"{self.value}[]"

    @property
    def concept_string(self) -> str:
        return f"{SpecialDomain.NATIVE}.{self.value}"

    @property
    def structure_class_name(self) -> str:
        return f"{self.value}Content"

    @classmethod
    def is_text_concept(cls, concept_code: str) -> bool:
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
                | NativeConceptCode.IMG_GEN_PROMPT
                | NativeConceptCode.PAGE
                | NativeConceptCode.ANYTHING
                | NativeConceptCode.JSON
            ):
                return False

    @classmethod
    def is_dynamic_concept(cls, concept_code: str) -> bool:
        try:
            enum_value = NativeConceptCode(concept_code)
        except ValueError:
            return False

        match enum_value:
            case (
                NativeConceptCode.TEXT
                | NativeConceptCode.IMAGE
                | NativeConceptCode.PDF
                | NativeConceptCode.TEXT_AND_IMAGES
                | NativeConceptCode.NUMBER
                | NativeConceptCode.IMG_GEN_PROMPT
                | NativeConceptCode.PAGE
                | NativeConceptCode.ANYTHING
                | NativeConceptCode.JSON
            ):
                return False
            case NativeConceptCode.DYNAMIC:
                return True

    @classmethod
    def values_list(cls) -> list["NativeConceptCode"]:
        return list(cls)

    @classmethod
    def native_concept_class_names(cls):
        return [native_concept.structure_class_name for native_concept in cls]

    @classmethod
    def is_native_concept_string_or_code(cls, concept_string_or_code: str) -> bool:
        if not is_concept_string_or_code_valid(concept_string_or_code=concept_string_or_code):
            return False

        if "." in concept_string_or_code:
            domain_code, concept_code = concept_string_or_code.split(".", 1)
            return SpecialDomain.is_native(domain=domain_code) and concept_code in cls.values_list()
        return concept_string_or_code in cls.values_list()

    @classmethod
    def validate_native_concept_string_or_code(cls, concept_string_or_code: str) -> None:
        if not cls.is_native_concept_string_or_code(concept_string_or_code=concept_string_or_code):
            msg = f"Concept string or code '{concept_string_or_code}' is not a valid native concept string or code"
            raise NativeConceptDefinitionError(msg)

    @classmethod
    def get_validated_native_concept_string(cls, concept_string_or_code: str) -> str:
        cls.validate_native_concept_string_or_code(concept_string_or_code=concept_string_or_code)
        if "." in concept_string_or_code:
            return concept_string_or_code
        else:
            return f"{SpecialDomain.NATIVE}.{concept_string_or_code}"
