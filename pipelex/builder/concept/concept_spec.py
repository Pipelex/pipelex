from datetime import datetime
from typing import Any

from pydantic import ConfigDict, Field, field_validator, model_validator

from pipelex import log
from pipelex.core.concepts.concept_blueprint import (
    ConceptBlueprint,
    ConceptBlueprintError,
    ConceptStructureBlueprint,
    ConceptStructureBlueprintError,
    ConceptStructureBlueprintFieldType,
)
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.concepts.exceptions import ConceptCodeError, ConceptStringOrConceptCodeError
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.system.registries.func_registry import pipe_func
from pipelex.tools.misc.string_utils import is_pascal_case, normalize_to_ascii, snake_to_pascal_case
from pipelex.types import Self, StrEnum


class ConceptStructureSpecFieldType(StrEnum):
    TEXT = "text"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    NUMBER = "number"
    DATE = "date"


class ConceptSpecError(Exception):
    pass


class ConceptStructureSpec(StructuredContent):
    """ConceptStructureSpec represents the schema for a single field in a concept's structure. It supports
    various field types including text, integer, boolean, number, and date.

    Attributes:
        the_field_name: Field name. Must be snake_case.
        description: Natural language description of the field's purpose and usage.
        type: The field's data type.
        required: Whether the field is mandatory. Defaults to True unless explicitly set to False.
        default_value: Default value for the field. Must match the specified type, and for choice
                      fields must be one of the valid choices. When provided, type must be specified
                      (unless choices are provided).

    Validation Rules:
        3. Default values: When default_value is provided:
           - For typed fields: type must be specified and default_value must match that type
           - Type validation includes: text (str), integer (int), boolean (bool),
             number (int/float), dict (dict)

    """

    the_field_name: str = Field(description="Field name. Must be snake_case.")
    description: str
    type: ConceptStructureSpecFieldType = Field(description="The type of the field.")
    required: bool | None = None
    default_value: Any | None = None

    @field_validator("type", mode="before")
    @classmethod
    def validate_type(cls, type_value: str) -> ConceptStructureSpecFieldType:
        return ConceptStructureSpecFieldType(type_value)

    @model_validator(mode="after")
    def validate_structure_blueprint(self) -> Self:
        """Validate the structure blueprint according to type rules."""
        # Check default_value type is the same as type
        if self.default_value is not None:
            self._validate_default_value_type()
        return self

    def _validate_default_value_type(self) -> None:
        """Validate that default_value matches the specified type."""
        if self.default_value is None:
            return

        match self.type:
            case ConceptStructureSpecFieldType.TEXT:
                if not isinstance(self.default_value, str):
                    self._raise_type_mismatch_error("str", type(self.default_value).__name__)
            case ConceptStructureSpecFieldType.INTEGER:
                if not isinstance(self.default_value, int):
                    self._raise_type_mismatch_error("int", type(self.default_value).__name__)
            case ConceptStructureSpecFieldType.BOOLEAN:
                if not isinstance(self.default_value, bool):
                    self._raise_type_mismatch_error("bool", type(self.default_value).__name__)
            case ConceptStructureSpecFieldType.NUMBER:
                if not isinstance(self.default_value, (int, float)):
                    self._raise_type_mismatch_error("number (int or float)", type(self.default_value).__name__)
            case ConceptStructureSpecFieldType.DATE:
                if not isinstance(self.default_value, datetime):
                    self._raise_type_mismatch_error("date", type(self.default_value).__name__)

    def _raise_type_mismatch_error(self, expected_type_name: str, actual_type_name: str) -> None:
        msg = f"default_value type mismatch: expected {expected_type_name} for type '{self.type}', but got {actual_type_name}"
        raise ConceptStructureBlueprintError(msg)

    def to_blueprint(self) -> ConceptStructureBlueprint:
        # Convert the type enum value - self.type is already a ConceptStructureBlueprintFieldType enum
        # We need to get the corresponding value in the core enum
        # Get the string value and use it to get the core enum value
        core_type = ConceptStructureBlueprintFieldType(self.type)

        return ConceptStructureBlueprint(
            description=self.description,
            type=core_type,
            required=self.required,
            default_value=self.default_value,
        )


class ConceptSpecDraft(StructuredContent):
    the_concept_code: str = Field(description="Concept code. Must be PascalCase.")
    description: str = Field(description="Description of the concept, in natural language.")
    structure: str = Field(
        description="Description of a dict with fieldnames as keys, and values being a dict with: description, type, required, default_value",
    )
    refines: str | None = Field(
        default=None,
        description="The native concept this concept extends (Text, Image, PDF, TextAndImages, Number, Page) "
        "in PascalCase format. Cannot be used together with 'structure'.",
    )


class ConceptSpec(StructuredContent):
    """Spec structuring a concept: a conceptual data type that can either define its own structure or refine an existing native concept.

    Validation Rules:
        1. Mutual exclusivity: A concept must have either 'structure' or 'refines', but not both.
        2. Field names: When structure is a dict, all keys must be valid snake_case identifiers.
        3. Concept codes: Must be in PascalCase format (letters and numbers only, starting
           with uppercase, no dots).
        4. Concept strings: Format is "domain.ConceptCode" where domain is lowercase and
           ConceptCode is PascalCase.
        5. Native concepts: When refining, must be one of the valid native concepts.
        6. Structure values: In structure attribute, values must be either valid concept strings
           or ConceptStructureBlueprint instances.
    """

    model_config = ConfigDict(extra="forbid")

    the_concept_code: str = Field(description="Name of the concept. Must be PascalCase.")
    description: str = Field(description="Description of the concept, in natural language.")
    structure: dict[str, ConceptStructureSpec] | None = Field(
        default=None,
        description=(
            "Definition of the concept's structure. Each attribute (snake_case) specifies: definition, type, and required or default_value if needed"
        ),
    )
    refines: str | None = Field(
        default=None,
        description=(
            "If applicable: the native concept this concept extends (Text, Image, PDF, TextAndImages, Number, Page) "
            "in PascalCase format. Cannot be used together with 'structure'."
        ),
    )

    @field_validator("the_concept_code", mode="before")
    @classmethod
    def validate_concept_code(cls, value: str) -> str:
        # Split first to handle domain.ConceptCode format
        if "." in value:
            domain, concept_code = value.split(".")
            # Only normalize the concept code part (not the domain)
            normalized_concept_code = normalize_to_ascii(concept_code)

            if normalized_concept_code != concept_code:
                log.warning(
                    f"Concept code '{value}' contained non-ASCII characters in concept part, normalized to '{domain}.{normalized_concept_code}'"
                )

            if not is_pascal_case(normalized_concept_code):
                log.warning(f"Concept code '{domain}.{normalized_concept_code}' is not PascalCase, converting to PascalCase")
                pascal_cased_value = snake_to_pascal_case(normalized_concept_code)
                return f"{domain}.{pascal_cased_value}"
            else:
                return f"{domain}.{normalized_concept_code}"
        else:
            # No dot, normalize the whole thing
            normalized_value = normalize_to_ascii(value)

            if normalized_value != value:
                log.warning(f"Concept code '{value}' contained non-ASCII characters, normalized to '{normalized_value}'")

            if not is_pascal_case(normalized_value):
                log.warning(f"Concept code '{normalized_value}' is not PascalCase, converting to PascalCase")
                return snake_to_pascal_case(normalized_value)
            else:
                return normalized_value

    @field_validator("refines", mode="before")
    @classmethod
    def validate_refines(cls, refines: str | None = None) -> str | None:
        if refines is not None:
            if not NativeConceptCode.get_validated_native_concept_string(concept_string_or_code=refines):
                msg = f"Forbidden to refine a non-native concept: '{refines}'. Refining non-native concepts will come soon."
                raise ConceptBlueprintError(msg)
        return refines

    @model_validator(mode="before")
    @classmethod
    def model_validate_spec(cls, values: dict[str, Any]) -> dict[str, Any]:
        if values.get("refines") and values.get("structure"):
            msg = (
                f"Forbidden to have refines and structure at the same time: `{values.get('refines')}` "
                f"and `{values.get('structure')}` for concept that has the description `{values.get('description')}`",
            )
            raise ConceptSpecError(msg)
        return values

    @classmethod
    def _post_validate_concept_code(cls, concept_code: str) -> None:
        if not is_pascal_case(concept_code):
            msg = (
                f"ConceptSpec _post_validate_concept_code: Concept code '{concept_code}' must be PascalCase "
                f"(letters and numbers only, starting with uppercase, without `.`)"
            )
            raise ConceptCodeError(msg)

    @classmethod
    def validate_concept_string_or_code(cls, concept_string_or_code: str) -> None:
        if concept_string_or_code.count(".") > 1:
            msg = (
                f"concept_string_or_code '{concept_string_or_code}' is invalid. "
                "It should either contain a domain in snake_case and a concept code in PascalCase separated by one dot, "
                "or be a concept code in PascalCase."
            )
            raise ConceptStringOrConceptCodeError(msg)

        if concept_string_or_code.count(".") == 1:
            domain, concept_code = concept_string_or_code.split(".")
            # Validate domain code
            DomainBlueprint.validate_domain_code(code=domain)
            cls._post_validate_concept_code(concept_code=concept_code)
        else:
            cls._post_validate_concept_code(concept_code=concept_string_or_code)

    def to_blueprint(self) -> ConceptBlueprint:
        """Convert this ConceptBlueprint to the original core ConceptBlueprint."""
        # TODO: Clarify concept structure blueprint
        converted_structure: str | dict[str, str | ConceptStructureBlueprint] | None = None
        if self.structure:
            converted_structure = {}
            for field_name, field_spec in self.structure.items():
                converted_structure[field_name] = field_spec.to_blueprint()

        return ConceptBlueprint(description=self.description, structure=converted_structure, refines=self.refines)


@pipe_func()
async def create_concept_spec(working_memory: WorkingMemory) -> ConceptSpec:
    concept_spec_draft = working_memory.get_stuff_as(name="concept_spec_draft", content_type=ConceptSpecDraft)
    concept_spec_structures_stuff = working_memory.get_stuff_as_list(name="concept_spec_structures", item_type=ConceptStructureSpec)

    structure_dict: dict[str, ConceptStructureSpec] = {}
    for structure_item in concept_spec_structures_stuff.items:
        structure_spec = ConceptStructureSpec(
            the_field_name=structure_item.the_field_name,
            description=structure_item.description,
            type=structure_item.type,
            required=structure_item.required,
            default_value=structure_item.default_value,
        )
        structure_dict[structure_item.the_field_name] = structure_spec

    return ConceptSpec(
        the_concept_code=concept_spec_draft.the_concept_code,
        description=concept_spec_draft.description,
        structure=structure_dict,
        refines=concept_spec_draft.refines,
    )
