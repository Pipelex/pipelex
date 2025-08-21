from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Self

from pipelex.core.concepts.concept_native import NativeConceptEnum
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
    refines: Optional[Union[str, List[str]]] = Field(default_factory=list)

    @staticmethod
    def validate_concept_code(concept_code: str) -> None:
        """Validate that a concept code follows PascalCase convention."""
        if not is_pascal_case(concept_code):
            raise ConceptBlueprintError(
                f"Concept code must be PascalCase (letters and numbers only, starting with uppercase) for concept code '{concept_code}'"
            )

    @staticmethod
    def validate_single_refine(refine: str) -> None:
        """Validate a single refine string, handling domain-qualified concept codes."""
        if "." in refine:
            # Count dots - there should be exactly one
            dot_count = refine.count(".")
            if dot_count != 1:
                raise ConceptBlueprintError(f"Refine with domain qualification must have exactly one dot, got {dot_count} dots in '{refine}'")

            # Split into domain and concept parts
            domain_part, concept_part = refine.split(".", 1)

            # Special case for native concepts
            if domain_part.lower() == SpecialDomain.NATIVE.value:
                # Check if the concept is a valid native concept
                valid_native_concepts = [native_concept.value for native_concept in NativeConceptEnum]
                if concept_part not in valid_native_concepts:
                    raise ConceptBlueprintError(
                        f"Invalid native concept '{concept_part}' in refine '{refine}'. Valid native concepts are: {valid_native_concepts}"
                    )
            else:
                # Validate domain part (should be snake_case)
                DomainBlueprint.validate_domain_code(domain_part)

                # Validate concept part (should be PascalCase)
                ConceptBlueprint.validate_concept_code(concept_part)
        else:
            # No dot, just validate as PascalCase concept code
            ConceptBlueprint.validate_concept_code(refine)

    @field_validator("refines", mode="after")
    @classmethod
    def validate_refines(cls, refines: Union[str, List[str]]) -> Union[str, List[str]]:
        if isinstance(refines, str):
            cls.validate_single_refine(refines)
        else:
            for refine in refines:
                cls.validate_single_refine(refine)
        return refines

    @model_validator(mode="before")
    def forbiden_having_refines_and_structure(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if values.get("refines") and values.get("structure"):
            raise ConceptBlueprintError(
                f"Forbidden to have refines and structure at the same time: `{values.get('refines')}` "
                f"and `{values.get('structure')}` for concept that has the definition `{values.get('definition')}`"
            )
        return values

    @model_validator(mode="after")
    def model_validate_blueprint(self) -> Self:
        return self

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
