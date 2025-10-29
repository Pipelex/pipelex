import re
from datetime import datetime
from typing import Any

from pydantic import ConfigDict, Field, field_validator, model_validator
from typing_extensions import override

from pipelex import log, pretty_print
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint, ConceptStructureBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprintFieldType
from pipelex.core.concepts.exceptions import ConceptStructureBlueprintValueError
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.concepts.exceptions import ConceptCodeError, ConceptBlueprintValueError
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.tools.misc.json_utils import remove_none_values_from_dict
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
        raise ConceptStructureBlueprintValueError(msg)

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

    @field_validator("refines", mode="before")
    @classmethod
    def validate_refines(cls, refines: str | None = None) -> str | None:
        if refines is not None:
            if not NativeConceptCode.get_validated_native_concept_string(concept_string_or_code=refines):
                msg = f"Forbidden to refine a non-native concept: '{refines}'. Refining non-native concepts will come soon."
                raise ConceptBlueprintValueError(msg)
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


    def to_blueprint(self) -> ConceptBlueprint:
        """Convert this ConceptBlueprint to the original core ConceptBlueprint."""
        # TODO: Clarify concept structure blueprint
        converted_structure: str | dict[str, str | ConceptStructureBlueprint] | None = None
        if self.structure:
            converted_structure = {}
            for field_name, field_spec in self.structure.items():
                converted_structure[field_name] = field_spec.to_blueprint()

        return ConceptBlueprint(description=self.description, structure=converted_structure, refines=self.refines)

    @override
    def pretty_print_content(self, title: str | None = None, number: int | None = None) -> None:
        the_dict: dict[str, Any] = self.smart_dump()
        the_dict = remove_none_values_from_dict(data=the_dict)
        if number:
            title = f"Concept #{number}: {self.the_concept_code}"
        else:
            title = f"Concept: {self.the_concept_code}"
        if self.refines:
            title += f" • Refines {self.refines}"
            the_dict.pop("refines")

        description = self.description
        the_dict.pop("the_concept_code")
        the_dict.pop("description")
        if self.structure:
            structure = the_dict.pop("structure")
            pretty_print(structure, title=title, subtitle=description)
        else:
            pretty_print(description, title=title)
