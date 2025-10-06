from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.concepts.exceptions import ConceptCodeError, ConceptStringError, ConceptStringOrConceptCodeError
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.tools.misc.string_utils import is_pascal_case
from pipelex.types import Self, StrEnum


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
    description: str
    type: ConceptStructureBlueprintFieldType | None = None
    item_type: str | None = None
    key_type: str | None = None
    value_type: str | None = None
    choices: list[str] | None = Field(default=None)
    required: bool | None = Field(default=True)
    default_value: Any | None = None

    # TODO: date translator for default_value

    @model_validator(mode="after")
    def validate_structure_blueprint(self) -> Self:
        """Validate the structure blueprint according to type rules."""
        # If type is None (array), choices must not be None
        if self.type is None and not self.choices:
            msg = f"When type is None (array), choices must not be empty. Actual type: {self.type}, choices: {self.choices}"
            raise ConceptStructureBlueprintError(msg)

        # If type is "dict", key_type and value_type must not be empty
        if self.type == ConceptStructureBlueprintFieldType.DICT:
            if not self.key_type:
                msg = f"When type is '{ConceptStructureBlueprintFieldType.DICT}', key_type must not be empty. Actual key_type: {self.key_type}"
                raise ConceptStructureBlueprintError(msg)
            if not self.value_type:
                msg = f"When type is '{ConceptStructureBlueprintFieldType.DICT}', value_type must not be empty. Actual value_type: {self.value_type}"
                raise ConceptStructureBlueprintError(msg)

        # Check when default_value is not None, type is not None (except for choice fields)
        if self.default_value is not None and self.type is None and not self.choices:
            msg = (
                f"When default_value is not None, type must be specified (unless choices are provided). Actual type: {self.type},"
                f"default_value: {self.default_value}, choices: {self.choices}"
            )
            raise ConceptStructureBlueprintError(msg)

        # Check default_value type is the same as type
        if self.default_value is not None and self.type is not None:
            self._validate_default_value_type()

        # Check default_value is valid for choice fields
        if self.default_value is not None and self.type is None and self.choices:
            if self.default_value not in self.choices:
                msg = f"default_value must be one of the valid choices. Got '{self.default_value}', valid choices: {self.choices}"
                raise ConceptStructureBlueprintError(msg)

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
        msg = f"default_value type mismatch: expected {expected_type_name} for type '{self.type}', but got {actual_type_name}"
        raise ConceptStructureBlueprintError(msg)


class ConceptBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str | None = None
    description: str
    # TODO (non-blockiing): define a type for Union[str, ConceptStructureBlueprint] (ConceptChoice to be consistent with LLMChoice)
    structure: str | dict[str, str | ConceptStructureBlueprint] | None = None
    # TODO: restore possibility of multiple refiles
    refines: str | None = None

    @classmethod
    def is_native_concept_code(cls, concept_code: str) -> bool:
        ConceptBlueprint.validate_concept_code(concept_code=concept_code)
        return NativeConceptCode.is_native_concept(concept_code=concept_code)

    @classmethod
    def validate_concept_code(cls, concept_code: str) -> None:
        if not is_pascal_case(concept_code):
            msg = (
                f"ConceptBlueprint validate_concept_code: Concept code '{concept_code}' must be PascalCase "
                f"(letters and numbers only, starting with uppercase, without `.`)"
            )
            raise ConceptCodeError(msg)

    @classmethod
    def validate_concept_string_or_code(cls, concept_string_or_code: str) -> None:
        if concept_string_or_code.count(".") > 1:
            msg = (
                f"concept_string_or_code '{concept_string_or_code}' is invalid. "
                "It should either contain a domain in snake_case and a concept code in PascalCase separated by one dot, "
                "or be a concept code in PascalCase.",
            )
            raise ConceptStringOrConceptCodeError(msg)

        if concept_string_or_code.count(".") == 1:
            domain, concept_code = concept_string_or_code.split(".")
            DomainBlueprint.validate_domain_code(code=domain)
            cls.validate_concept_code(concept_code=concept_code)
        else:
            cls.validate_concept_code(concept_code=concept_string_or_code)

    @staticmethod
    def validate_concept_string(concept_string: str) -> None:
        """Validate that a concept code follows PascalCase convention."""
        if "." not in concept_string or concept_string.count(".") > 1:
            msg = (
                f"Concept string '{concept_string}' is invalid. It should contain a domain in snake_case "
                "and a concept code in PascalCase separated by one dot."
            )
            raise ConceptStringError(msg)
        domain, concept_code = concept_string.split(".", 1)

        # Validate domain
        DomainBlueprint.validate_domain_code(domain)

        # Validate concept code
        if not is_pascal_case(concept_code):
            msg = (
                f"ConceptBlueprint validate_concept_string: Concept code '{concept_code}' must be PascalCase "
                f"(letters and numbers only, starting with uppercase, without `.`)"
            )
            raise ConceptCodeError(msg)

        # Validate that if the concept code is among the native concepts, the domain MUST be native.
        if concept_code in NativeConceptCode.values_list():
            if not SpecialDomain.is_native(domain=domain):
                msg = (
                    f"Concept string '{concept_string}' is invalid. "
                    f"Concept code '{concept_code}' is a native concept, so the domain must be '{SpecialDomain.NATIVE}', "
                    f"or nothing, but not '{domain}'"
                )
                raise ConceptStringError(msg)
        # Validate that if the domain is native, the concept code is a native concept
        if SpecialDomain.is_native(domain=domain):
            if concept_code not in NativeConceptCode.values_list():
                msg = (
                    f"Concept string '{concept_string}' is invalid. "
                    f"Concept code '{concept_code}' is not a native concept, so the domain must not be '{SpecialDomain.NATIVE}'."
                )
                raise ConceptStringError(msg)

    @field_validator("refines", mode="before")
    @classmethod
    def validate_refines(cls, refines: str | None = None) -> str | None:
        if refines is not None:
            if not NativeConceptCode.get_validated_native_concept_string(concept_string_or_code=refines):
                msg = f"Refine '{refines}' is not a native concept and we currently can only refine native concepts"
                raise ConceptBlueprintError(msg)
        return refines

    @model_validator(mode="before")
    @classmethod
    def model_validate_blueprint(cls, values: dict[str, Any] | str) -> dict[str, Any] | str:
        if isinstance(values, dict) and values.get("refines") and values.get("structure"):
            msg = (
                f"Forbidden to have refines and structure at the same time: `{values.get('refines')}` "
                f"and `{values.get('structure')}` for concept that has the definition `{values.get('description')}`"
            )
            raise ConceptBlueprintError(msg)
        return values
