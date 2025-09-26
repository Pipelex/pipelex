from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Self

from pipelex.core.concepts.concept_native import NativeConceptEnum, NativeConceptManager
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
    type: Optional[ConceptStructureBlueprintFieldType] = None
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

        match self.type:
            case ConceptStructureBlueprintFieldType.TEXT:
                if not isinstance(self.default_value, str):
                    self._raise_type_mismatch_error("str", type(self.default_value).__name__)
            case ConceptStructureBlueprintFieldType.INTEGER:
                if not isinstance(self.default_value, int):
                    self._raise_type_mismatch_error("int", type(self.default_value).__name__)
            case ConceptStructureBlueprintFieldType.BOOLEAN:
                if not isinstance(self.default_value, bool):
                    self._raise_type_mismatch_error("bool", type(self.default_value).__name__)
            case ConceptStructureBlueprintFieldType.NUMBER:
                if not isinstance(self.default_value, (int, float)):
                    self._raise_type_mismatch_error("number (int or float)", type(self.default_value).__name__)
            case ConceptStructureBlueprintFieldType.LIST:
                if not isinstance(self.default_value, list):
                    self._raise_type_mismatch_error("list", type(self.default_value).__name__)
            case ConceptStructureBlueprintFieldType.DICT:
                if not isinstance(self.default_value, dict):
                    self._raise_type_mismatch_error("dict", type(self.default_value).__name__)
            case ConceptStructureBlueprintFieldType.DATE:
                if not isinstance(self.default_value, datetime):
                    self._raise_type_mismatch_error("date", type(self.default_value).__name__)

    def _raise_type_mismatch_error(self, expected_type_name: str, actual_type_name: str) -> None:
        """Raise a type mismatch error with consistent formatting."""
        raise ConceptStructureBlueprintError(
            f"default_value type mismatch: expected {expected_type_name} for type '{self.type}', but got {actual_type_name}"
        )


class ConceptBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    definition: str
    # TODO (non-blockiing): define a type for Union[str, ConceptStructureBlueprint] (ConceptChoice to be consistent with LLMChoice)
    structure: Optional[Union[str, Dict[str, Union[str, ConceptStructureBlueprint]]]] = None
    # TODO: restore possibility of multiple refiles
    refines: Optional[str] = None

    @classmethod
    def is_native_concept_code(cls, concept_code: str) -> bool:
        ConceptBlueprint.validate_concept_code(concept_code=concept_code)
        return concept_code in [native_concept for native_concept in NativeConceptEnum]

    @classmethod
    def validate_concept_code(cls, concept_code: str) -> None:
        if not is_pascal_case(concept_code):
            raise ConceptCodeError(
                f"Concept code '{concept_code}' must be PascalCase (letters and numbers only, starting with uppercase, without `.`)"
            )

    @classmethod
    def validate_concept_string_or_code(cls, concept_string_or_code: str) -> None:
        if concept_string_or_code.count(".") > 1:
            raise ConceptStringOrConceptCodeError(
                f"concept_string_or_code '{concept_string_or_code}' is invalid. "
                "It should either contain a domain in snake_case and a concept code in PascalCase separated by one dot, "
                "or be a concept code in PascalCase."
            )

        elif concept_string_or_code.count(".") == 1:
            domain, concept_code = concept_string_or_code.split(".")
            DomainBlueprint.validate_domain_code(code=domain)
            cls.validate_concept_code(concept_code=concept_code)
        else:
            cls.validate_concept_code(concept_code=concept_string_or_code)

    @staticmethod
    def validate_concept_string(concept_string: str) -> None:
        """Validate that a concept code follows PascalCase convention."""
        if "." not in concept_string:
            raise ConceptStringError(
                f"Concept string '{concept_string}' is invalid. It should contain a domain in snake_case "
                "and a concept code in PascalCase separated by one dot."
            )
        elif concept_string.count(".") > 1:
            raise ConceptStringError(
                f"Concept string '{concept_string}' is invalid. It should contain a domain in snake_case "
                "and a concept code in PascalCase separated by one dot."
            )
        else:
            domain, concept_code = concept_string.split(".", 1)

        # Validate domain
        DomainBlueprint.validate_domain_code(domain)

        # Validate concept code
        if not is_pascal_case(concept_code):
            raise ConceptCodeError(
                f"Concept code '{concept_code}' must be PascalCase (letters and numbers only, starting with uppercase, without `.`)"
            )

        # Validate that if the concept code is among the native concepts, the domain MUST be native.
        if concept_code in [concept.value for concept in [native_concept for native_concept in NativeConceptEnum]]:
            if not SpecialDomain.is_native(domain=domain):
                raise ConceptStringError(
                    f"Concept string '{concept_string}' is invalid. "
                    f"Concept code '{concept_code}' is a native concept, so the domain must be '{SpecialDomain.NATIVE}', "
                    f"or nothing, but not '{domain}'"
                )

        # Validate that if the domain is native, the concept code is a native concept
        if SpecialDomain.is_native(domain=domain):
            if concept_code not in [native_concept for native_concept in NativeConceptEnum]:
                raise ConceptStringError(
                    f"Concept string '{concept_string}' is invalid. "
                    f"Concept code '{concept_code}' is not a native concept, so the domain must not be '{SpecialDomain.NATIVE}'."
                )

    @field_validator("refines", mode="before")
    @classmethod
    def validate_refines(cls, refines: Optional[str] = None) -> Optional[str]:
        if refines is not None:
            if not NativeConceptManager.is_native_concept(refines):
                raise ConceptBlueprintError(f"Forbidden to refine a non-native concept: '{refines}'. Refining non-native concepts will come soon.")
            cls.validate_concept_string_or_code(concept_string_or_code=refines)
        return refines

    @model_validator(mode="before")
    def model_validate_blueprint(cls, values: Union[Dict[str, Any], str]) -> Union[Dict[str, Any], str]:
        if isinstance(values, dict) and values.get("refines") and values.get("structure"):
            raise ConceptBlueprintError(
                f"Forbidden to have refines and structure at the same time: `{values.get('refines')}` "
                f"and `{values.get('structure')}` for concept that has the definition `{values.get('definition')}`"
            )
        return values
