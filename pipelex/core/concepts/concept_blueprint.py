from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Self

from pipelex.core.concepts.concept_native import NativeConceptEnum
from pipelex.core.concepts.exceptions import ConceptCodeError, ConceptStringError, ConceptStringOrConceptCodeError
from pipelex.core.domains.domain import DomainBlueprint, SpecialDomain
from pipelex.tools.misc.string_utils import is_pascal_case
from pipelex.types import StrEnum


class ConceptBlueprintError(Exception):
    pass


class ConceptStructureBlueprintError(Exception):
    pass


class ConceptStructureBlueprintFieldType(StrEnum):
    TEXT = "text"
    LIST = "list"
    DICT = "dict"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    NUMBER = "number"
    DATE = "date"


class ConceptStructureBlueprint(BaseModel):
    definition: str
    type: ConceptStructureBlueprintFieldType | None = None
    item_type: Optional[str] = None
    key_type: Optional[str] = None
    value_type: Optional[str] = None
    choices: Optional[List[str]] = Field(default_factory=list)
    required: Optional[bool] = Field(default=True)
    default_value: Optional[Any] = None

    # TODO: date translator for default_value
    # TODO: check default_value type is the same as type
    # TODO: check when default_value is not None, type is not None

    @model_validator(mode="after")
    def validate_structure_blueprint(self) -> Self:
        """Validate the structure blueprint according to type rules."""
        # If type is None (array), choices must not be None
        if self.type is None and not self.choices:
            raise ConceptStructureBlueprintError("When type is None (array), choices must not be empty")

        # If type is "dict", key_type and value_type must not be empty
        if self.type == ConceptStructureBlueprintFieldType.DICT:
            if not self.key_type:
                raise ConceptStructureBlueprintError(f"When type is '{ConceptStructureBlueprintFieldType.DICT}', key_type must not be empty")
            if not self.value_type:
                raise ConceptStructureBlueprintError(f"When type is '{ConceptStructureBlueprintFieldType.DICT}', value_type must not be empty")

        return self


ConceptStructureBlueprintType = Union[str, ConceptStructureBlueprint]


class ConceptBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    definition: str
    structure: Optional[Union[str, Dict[str, ConceptStructureBlueprintType]]] = None
    refines: Optional[str] = None

    @classmethod
    def is_native_concept_code(cls, concept_code: str) -> bool:
        ConceptBlueprint.validate_concept_code(concept_code=concept_code)
        return concept_code in [native_concept.value for native_concept in NativeConceptEnum]

    @classmethod
    def is_native_concept_string_or_concept_code(cls, concept_string_or_concept_code: str) -> bool:
        if "." in concept_string_or_concept_code:
            domain, concept_code = concept_string_or_concept_code.split(".", 1)
            if domain == SpecialDomain.NATIVE.value and concept_code in [native_concept.value for native_concept in NativeConceptEnum]:
                return True
        else:
            if concept_string_or_concept_code in [native_concept.value for native_concept in NativeConceptEnum]:
                return True
        return False

    @classmethod
    def validate_concept_code(cls, concept_code: str) -> None:
        if not is_pascal_case(concept_code):
            raise ConceptCodeError(code=concept_code)

    @classmethod
    def validate_concept_string_or_concept_code(cls, concept_string_or_concept_code: str) -> None:
        if concept_string_or_concept_code.count(".") > 1:
            raise ConceptStringOrConceptCodeError(concept_string_or_concept_code=concept_string_or_concept_code)

        elif concept_string_or_concept_code.count(".") == 1:
            domain, concept_code = concept_string_or_concept_code.split(".")
            DomainBlueprint.validate_domain_code(code=domain)
            cls.validate_concept_code(concept_code=concept_code)
        else:
            cls.validate_concept_code(concept_code=concept_string_or_concept_code)

    @staticmethod
    def validate_concept_string(concept_string: str) -> None:
        """Validate that a concept code follows PascalCase convention."""
        if "." not in concept_string:
            raise ConceptStringError(concept_string)
        elif concept_string.count(".") > 1:
            raise ConceptStringError(concept_string)
        else:
            domain, concept_code = concept_string.split(".", 1)

        # Validate domain
        DomainBlueprint.validate_domain_code(domain)

        # Validate concept code
        if not is_pascal_case(concept_code):
            raise ConceptCodeError(code=concept_code)

        # Validate that if the concept code is among the native concepts, the domain MUST be native.
        if concept_code in [native_concept.value for native_concept in NativeConceptEnum]:
            if domain != SpecialDomain.NATIVE.value:
                raise ConceptStringError(
                    concept_string,
                    f"Concept code '{concept_code}' is a native concept, so the domain must be '{SpecialDomain.NATIVE.value}', "
                    "or nothing, but not '{domain}'",
                )

        # Validate that if the domain is native, the concept code is a native concept
        if domain == SpecialDomain.NATIVE.value:
            if concept_code not in [native_concept.value for native_concept in NativeConceptEnum]:
                raise ConceptStringError(
                    concept_string,
                    f"Concept code '{concept_code}' is not a native concept, so the domain must be '{SpecialDomain.NATIVE.value}', or nothing.",
                )

    @field_validator("refines", mode="before")
    @classmethod
    def validate_refines(cls, refines: Optional[str] = None) -> Optional[str]:
        def is_native_concept(concept_ref: str) -> bool:
            """Check if a concept reference is a native concept (short or fully qualified form)."""
            native_concept_values = [native_concept.value for native_concept in NativeConceptEnum]

            # Check short form (e.g., "Text")
            if concept_ref in native_concept_values:
                return True

            # Check fully qualified form (e.g., "native.Text")
            if "." in concept_ref:
                domain, concept_code = concept_ref.split(".", 1)
                if domain == SpecialDomain.NATIVE.value and concept_code in native_concept_values:
                    return True

            return False

        if refines is not None:
            if not is_native_concept(refines):
                raise ConceptBlueprintError(f"Forbidden to refine a non-native concept: '{refines}'. Refining non-native concepts will come soon.")
            cls.validate_concept_string_or_concept_code(concept_string_or_concept_code=refines)
        return refines

    @classmethod
    def forbiden_having_refines_and_structure(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if values.get("refines") and values.get("structure"):
            raise ConceptBlueprintError(
                f"Forbidden to have refines and structure at the same time: `{values.get('refines')}` "
                f"and `{values.get('structure')}` for concept that has the definition `{values.get('definition')}`"
            )
        return values

    @model_validator(mode="before")
    def model_validate_blueprint(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(values, ConceptBlueprint):
            cls.forbiden_having_refines_and_structure(values=values)
        return values

    def structure_to_field_def(self) -> Dict[str, Any]:
        # TODO: Refactor this method
        if isinstance(self.structure, str):
            raise ValueError("structure_to_field_def can only be called when structure is a dict in the blueprint")

        if self.structure is None:
            return {}

        # Process the dict structure
        result: Dict[str, Any] = {}
        for key, value in self.structure.items():
            if isinstance(value, ConceptStructureBlueprint):
                # Use model_dump for ConceptStructureBlueprint instances
                result[key] = value.model_dump()
            else:
                # This shouldn't happen based on the type hints, but handle it gracefully
                result[key] = {"type": ConceptStructureBlueprintFieldType.TEXT, "definition": value}

        return result

    @staticmethod
    def extract_non_native_refines(refines: Union[str, List[str]]) -> List[str]:
        if isinstance(refines, str) and "." not in refines:
            if refines not in [native_concept.value for native_concept in NativeConceptEnum]:
                return [refines]
        elif isinstance(refines, list):
            to_return: List[str] = []
            for refine in refines:
                to_return += ConceptBlueprint.extract_non_native_refines(refine)
            return to_return
        return []
