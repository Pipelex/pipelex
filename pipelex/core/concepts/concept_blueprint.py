from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Self

from pipelex.core.concepts.concept_native import NativeConceptEnum
from pipelex.core.concepts.exceptions import ConceptCodeError, ConceptStringError, ConceptStringOrConceptCodeError
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.domains.domain_blueprint import DomainBlueprint
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

    @model_validator(mode="after")
    def validate_structure_blueprint(self) -> Self:
        """Validate the structure blueprint according to type rules."""
        # If type is None (array), choices must not be None
        if self.type is None and not self.choices:
            raise ConceptStructureBlueprintError(
                f"When type is None (array), choices must not be empty. Actual type: {self.type}, choices: {self.choices}"
            )

        # If type is "dict", key_type and value_type must not be empty
        if self.type == ConceptStructureBlueprintFieldType.DICT:
            if not self.key_type:
                raise ConceptStructureBlueprintError(
                    f"When type is '{ConceptStructureBlueprintFieldType.DICT}', key_type must not be empty. Actual key_type: {self.key_type}"
                )
            if not self.value_type:
                raise ConceptStructureBlueprintError(
                    f"When type is '{ConceptStructureBlueprintFieldType.DICT}', value_type must not be empty. Actual value_type: {self.value_type}"
                )

        # Check when default_value is not None, type is not None (except for choice fields)
        if self.default_value is not None and self.type is None and not self.choices:
            raise ConceptStructureBlueprintError(
                f"When default_value is not None, type must be specified (unless choices are provided). "
                f"Actual type: {self.type}, default_value: {self.default_value}, choices: {self.choices}"
            )

        # Check default_value type is the same as type
        if self.default_value is not None and self.type is not None:
            self._validate_default_value_type()

        # Check default_value is valid for choice fields
        if self.default_value is not None and self.type is None and self.choices:
            if self.default_value not in self.choices:
                raise ConceptStructureBlueprintError(
                    f"default_value must be one of the valid choices. Got '{self.default_value}', valid choices: {self.choices}"
                )

        return self

    def _validate_default_value_type(self) -> None:
        """Validate that default_value matches the specified type."""
        if self.type is None or self.default_value is None:
            return

        # Validate based on the type
        if self.type == ConceptStructureBlueprintFieldType.TEXT:
            if not isinstance(self.default_value, str):
                self._raise_type_mismatch_error("str", type(self.default_value).__name__)
        elif self.type == ConceptStructureBlueprintFieldType.INTEGER:
            if not isinstance(self.default_value, int):
                self._raise_type_mismatch_error("int", type(self.default_value).__name__)
        elif self.type == ConceptStructureBlueprintFieldType.BOOLEAN:
            if not isinstance(self.default_value, bool):
                self._raise_type_mismatch_error("bool", type(self.default_value).__name__)
        elif self.type == ConceptStructureBlueprintFieldType.NUMBER:
            if not isinstance(self.default_value, (int, float)):
                self._raise_type_mismatch_error("number (int or float)", type(self.default_value).__name__)
        elif self.type == ConceptStructureBlueprintFieldType.LIST:
            if not isinstance(self.default_value, list):
                self._raise_type_mismatch_error("list", type(self.default_value).__name__)
        elif self.type == ConceptStructureBlueprintFieldType.DICT:
            if not isinstance(self.default_value, dict):
                self._raise_type_mismatch_error("dict", type(self.default_value).__name__)
        # Skip validation for DATE and other unknown types

    def _raise_type_mismatch_error(self, expected_type_name: str, actual_type_name: str) -> None:
        """Raise a type mismatch error with consistent formatting."""
        raise ConceptStructureBlueprintError(
            f"default_value type mismatch: expected {expected_type_name} for type '{self.type}', but got {actual_type_name}"
        )


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
