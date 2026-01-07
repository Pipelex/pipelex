from pipelex.core.concepts.native.exceptions import NativeConceptDefinitionError
from pipelex.core.concepts.validation import is_concept_ref_or_code_valid
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.dynamic_content import DynamicContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.types import StrEnum


class NativeConceptCode(StrEnum):
    DYNAMIC = "Dynamic"
    TEXT = "Text"
    IMAGE = "Image"
    DOCUMENT = "Document"
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
    def concept_ref(self) -> str:
        return f"{SpecialDomain.NATIVE}.{self.value}"

    @property
    def structure_class_name(self) -> str:
        return f"{self.value}Content"

    @property
    def structure_class(self) -> type | None:
        """Get the structure class for this native concept.

        Returns:
            The structure class, or None if this concept doesn't have a dedicated content class
        """
        match self:
            case NativeConceptCode.DYNAMIC:
                return DynamicContent
            case NativeConceptCode.TEXT:
                return TextContent
            case NativeConceptCode.IMAGE:
                return ImageContent
            case NativeConceptCode.DOCUMENT:
                return DocumentContent
            case NativeConceptCode.TEXT_AND_IMAGES:
                return TextAndImagesContent
            case NativeConceptCode.NUMBER:
                return NumberContent
            case NativeConceptCode.PAGE:
                return PageContent
            case NativeConceptCode.JSON:
                return JSONContent
            case NativeConceptCode.IMG_GEN_PROMPT | NativeConceptCode.ANYTHING:
                # These don't have dedicated content classes
                return None

    @classmethod
    def is_native_structure_class(cls, class_name: str) -> bool:
        """Check if a class name is a native structure class.

        Args:
            class_name: The class name to check

        Returns:
            True if it's a native structure class
        """
        return class_name in cls.native_concept_class_names()

    @classmethod
    def get_native_structure_class(cls, class_name: str) -> type | None:
        """Get the native structure class by name.

        Args:
            class_name: The class name to look up

        Returns:
            The structure class, or None if not found
        """
        if not cls.is_native_structure_class(class_name):
            msg = f"Class name '{class_name}' is not a native structure class"
            raise NativeConceptDefinitionError(msg)
        for native_code in cls:
            if native_code.structure_class_name == class_name:
                return native_code.structure_class
        return None

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
                | NativeConceptCode.DOCUMENT
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
                | NativeConceptCode.DOCUMENT
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
    def is_native_concept_ref_or_code(cls, concept_ref_or_code: str) -> bool:
        if not is_concept_ref_or_code_valid(concept_ref_or_code=concept_ref_or_code):
            return False

        if "." in concept_ref_or_code:
            domain_code, concept_code = concept_ref_or_code.split(".", 1)
            return SpecialDomain.is_native(domain_code=domain_code) and concept_code in cls.values_list()
        return concept_ref_or_code in cls.values_list()

    @classmethod
    def is_valid_native_concept_ref(cls, concept_ref: str) -> bool:
        """Check if the string is a valid native concept string (e.g., native.Text, native.Image).

        Unlike is_native_concept_ref_or_code, this method requires the full concept string
        with the native domain prefix (e.g., "native.Text" is valid, but "Text" alone is not).

        Args:
            concept_ref: The concept string to validate

        Returns:
            True if the string is a valid native concept string with domain prefix
        """
        if "." not in concept_ref:
            return False
        domain_code, concept_code = concept_ref.split(".", 1)
        return SpecialDomain.is_native(domain_code=domain_code) and concept_code in cls.values_list()

    @classmethod
    def validate_native_concept_ref_or_code(cls, concept_ref_or_code: str) -> None:
        if not cls.is_native_concept_ref_or_code(concept_ref_or_code=concept_ref_or_code):
            msg = f"Concept string or code '{concept_ref_or_code}' is not a valid native concept string or code"
            raise NativeConceptDefinitionError(msg)

    @classmethod
    def get_validated_native_concept_ref(cls, concept_ref_or_code: str) -> str:
        cls.validate_native_concept_ref_or_code(concept_ref_or_code=concept_ref_or_code)
        if "." in concept_ref_or_code:
            return concept_ref_or_code
        else:
            return f"{SpecialDomain.NATIVE}.{concept_ref_or_code}"
