from datetime import datetime
from enum import StrEnum
from typing import Any, Self, cast

from pydantic import ConfigDict, Field, field_validator, model_validator
from rich.console import Group
from rich.table import Table
from rich.text import Text
from typing_extensions import override

from pipelex import log
from pipelex.builder.concept.exceptions import ConceptSpecError
from pipelex.cogt.content_generation.dry_run_factory import MockFormat
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint, ConceptStructureBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprintFieldType
from pipelex.core.concepts.validation import is_concept_ref_or_code_valid
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.tools.misc.pretty import PrettyPrintable
from pipelex.tools.misc.string_utils import is_pascal_case, normalize_to_ascii, snake_to_pascal_case


class ConceptStructureSpecFieldType(StrEnum):
    TEXT = "text"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    NUMBER = "number"
    DATE = "date"
    CONCEPT = "concept"
    LIST = "list"

    @property
    def is_text(self) -> bool:
        match self:
            case ConceptStructureSpecFieldType.TEXT:
                return True
            case (
                ConceptStructureSpecFieldType.INTEGER
                | ConceptStructureSpecFieldType.BOOLEAN
                | ConceptStructureSpecFieldType.NUMBER
                | ConceptStructureSpecFieldType.DATE
                | ConceptStructureSpecFieldType.CONCEPT
                | ConceptStructureSpecFieldType.LIST
            ):
                return False


class ConceptStructureSpec(StructuredContent):
    """ConceptStructureSpec represents the schema for a single field in a concept's structure. It supports
    various field types including text, integer, boolean, number, date, and concept.

    Attributes:
        the_field_name: Field name. Must be snake_case.
        description: Natural language description of the field's purpose and usage.
        type: The field's data type.
        required: Whether the field is mandatory. Defaults to False unless explicitly set to True.
        default_value: Default value for the field. Must match the specified type.
        concept_ref: For type="concept", the reference to the concept (e.g., "myapp.Customer").

    Validation Rules:
        1. CONCEPT type: concept_ref must be set; default_value cannot be set.
        3. Default values: When default_value is provided, it must match the specified type.

    """

    the_field_name: str = Field(description="Field name. Must be snake_case.", json_schema_extra={"mock_format": MockFormat.SNAKE_CASE})
    description: str
    # TODO: Change examples to list(ConceptStructureSpecFieldType) for randomness in mocks
    type: ConceptStructureSpecFieldType = Field(description="The type of the field.", examples=["concept"])
    required: bool = Field(default=False, description="Whether the field is mandatory. Defaults to False unless explicitly set to True.")
    default_value: Any | None = Field(default=None, json_schema_extra={"mock_format": MockFormat.IGNORE})
    concept_ref: str | None = Field(
        default=None,
        description="For type='concept', the concept reference (e.g., 'myapp.Customer').",
        json_schema_extra={"mock_format": MockFormat.CONCEPT_REF},
    )
    choices: list[str] | None = Field(
        default=None, description="List of allowed values for the field. When set, the field value must be one of these choices."
    )
    item_type: str | None = Field(
        default=None,
        description="For type='list', the type of items in the list (e.g., 'text', 'concept').",
    )
    item_concept_ref: str | None = Field(
        default=None,
        description="For type='list' with item_type='concept', the concept reference for list items.",
        json_schema_extra={"mock_format": MockFormat.CONCEPT_REF},
    )

    @model_validator(mode="before")
    @classmethod
    def default_type_for_choices(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Default type to TEXT when choices is present but type is omitted."""
        if values.get("choices") and not values.get("type"):
            values["type"] = "text"
        return values

    @field_validator("type", mode="before")
    @classmethod
    def validate_type(cls, type_value: str) -> ConceptStructureSpecFieldType:
        return ConceptStructureSpecFieldType(type_value)

    @model_validator(mode="after")
    def validate_structure_blueprint(self) -> Self:
        """Validate the structure blueprint according to type rules."""
        match self.type:
            case ConceptStructureSpecFieldType.CONCEPT:
                if not self.concept_ref:
                    msg = "When type is 'concept', concept_ref must be set."
                    raise ValueError(msg)
                if self.default_value is not None:
                    msg = "default_value cannot be set for concept type (complex objects cannot have defaults)."
                    raise ValueError(msg)

            case ConceptStructureSpecFieldType.LIST:
                if not self.item_type:
                    msg = "When type is 'list', item_type must be set."
                    raise ValueError(msg)
                if self.item_type == "concept" and not self.item_concept_ref:
                    msg = "When item_type is 'concept', item_concept_ref must be set."
                    raise ValueError(msg)
                if self.item_concept_ref and self.item_type != "concept":
                    msg = f"item_concept_ref can only be set when item_type is 'concept'. Actual item_type: {self.item_type}"
                    raise ValueError(msg)
                if self.default_value is not None:
                    msg = "default_value cannot be set for list type."
                    raise ValueError(msg)

            case (
                ConceptStructureSpecFieldType.TEXT
                | ConceptStructureSpecFieldType.INTEGER
                | ConceptStructureSpecFieldType.BOOLEAN
                | ConceptStructureSpecFieldType.NUMBER
                | ConceptStructureSpecFieldType.DATE
            ):
                pass

        # Validate concept_ref can only be set when type is 'concept'
        if self.concept_ref and self.type != ConceptStructureSpecFieldType.CONCEPT:
            msg = f"'concept_ref' can only be set when type is 'concept'. Actual type: {self.type}"
            raise ValueError(msg)

        # Validate item_type and item_concept_ref can only be set when type is 'list'
        if self.item_type and self.type != ConceptStructureSpecFieldType.LIST:
            msg = f"'item_type' can only be set when type is 'list'. Actual type: {self.type}"
            raise ValueError(msg)
        if self.item_concept_ref and self.type != ConceptStructureSpecFieldType.LIST:
            msg = f"'item_concept_ref' can only be set when type is 'list'. Actual type: {self.type}"
            raise ValueError(msg)

        # Validate choices is only compatible with text, integer, and number types
        if self.choices:
            match self.type:
                case ConceptStructureSpecFieldType.TEXT | ConceptStructureSpecFieldType.INTEGER | ConceptStructureSpecFieldType.NUMBER:
                    pass
                case (
                    ConceptStructureSpecFieldType.BOOLEAN
                    | ConceptStructureSpecFieldType.DATE
                    | ConceptStructureSpecFieldType.CONCEPT
                    | ConceptStructureSpecFieldType.LIST
                ):
                    msg = f"'choices' cannot be used with type '{self.type}'. Only text, integer, and number types support choices."
                    raise ValueError(msg)

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
                    self._raise_type_mismatch_error("str", actual_type_name=type(self.default_value).__name__)
            case ConceptStructureSpecFieldType.INTEGER:
                if not isinstance(self.default_value, int):
                    self._raise_type_mismatch_error("int", actual_type_name=type(self.default_value).__name__)
            case ConceptStructureSpecFieldType.BOOLEAN:
                if not isinstance(self.default_value, bool):
                    self._raise_type_mismatch_error("bool", actual_type_name=type(self.default_value).__name__)
            case ConceptStructureSpecFieldType.NUMBER:
                if not isinstance(self.default_value, (int, float)):
                    self._raise_type_mismatch_error("number (int or float)", actual_type_name=type(self.default_value).__name__)
            case ConceptStructureSpecFieldType.DATE:
                if not isinstance(self.default_value, datetime):
                    self._raise_type_mismatch_error("date", actual_type_name=type(self.default_value).__name__)
            case ConceptStructureSpecFieldType.CONCEPT:
                # CONCEPT type cannot have default values, this is already validated in validate_structure_blueprint
                pass
            case ConceptStructureSpecFieldType.LIST:
                # LIST type cannot have default values, this is already validated in validate_structure_blueprint
                pass

    def _raise_type_mismatch_error(self, expected_type_name: str, *, actual_type_name: str) -> None:
        msg = f"default_value type mismatch: expected {expected_type_name} for type '{self.type}', but got {actual_type_name}"
        raise ValueError(msg)

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
            concept_ref=self.concept_ref,
            choices=self.choices,
            item_type=self.item_type,
            item_concept_ref=self.item_concept_ref,
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

    concept_code: str = Field(description="Name of the concept. Must be PascalCase.", json_schema_extra={"mock_format": MockFormat.PASCAL_CASE})
    description: str = Field(description="Description of the concept, in natural language.")
    structure: dict[str, ConceptStructureSpec] | None = Field(
        default=None,
        description=(
            "Definition of the concept's structure. Each attribute (snake_case) specifies: definition, type, and required or default_value if needed"
        ),
        json_schema_extra={"mock_format": MockFormat.IGNORE},
    )
    refines: str | None = Field(
        default=None,
        description=(
            "If applicable: the native concept this concept extends "
            "(Text, Html, Image, Document, Number, Page, TextAndImages, JSON, Anything, Dynamic) "
            "in PascalCase format. Cannot be used together with 'structure'."
        ),
        examples=["Text", "Html", "Image", "Document", "Number", "Page", "TextAndImages", "JSON"],
    )

    @field_validator("concept_code", mode="before")
    @classmethod
    def validate_concept_code(cls, value: str) -> str:
        # Split first to handle domain.ConceptCode format
        if "." in value:
            domain, concept_code = value.rsplit(".", 1)
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
        """Validate the refines field.

        Refines can be either:
        - A native concept ref (e.g., "native.Text", "Text")
        - A non-native concept ref (e.g., "myapp.BaseEntity") for concept-to-concept inheritance

        Non-native concept refs are allowed since dependencies are loaded in topological order,
        ensuring the refined concept exists before the refining concept is constructed.
        """
        if refines is None:
            return None

        # Check if it's a valid concept ref or code (domain.ConceptCode or ConceptCode in PascalCase)
        if is_concept_ref_or_code_valid(concept_ref_or_code=refines):
            return refines

        # Invalid refines value
        msg = f"Refines '{refines}' must be a valid concept ref (domain.ConceptCode) or concept code (PascalCase)"
        raise ValueError(msg)

    @model_validator(mode="before")
    @classmethod
    def model_validate_spec(cls, values: Any) -> Any:
        # mode="before" receives raw, unvalidated input — a non-dict (e.g. a plain string in a
        # `ConceptSpec | str` union) must fall through untouched rather than crash on dict access
        if not isinstance(values, dict):
            return values
        fields = cast("dict[str, Any]", values)
        if fields.get("refines") and fields.get("structure"):
            msg = (
                f"Forbidden to have refines and structure at the same time: `{fields.get('refines')}` "
                f"and `{fields.get('structure')}` for concept that has the description `{fields.get('description')}`"
            )
            raise ConceptSpecError(msg)
        return fields

    def to_blueprint(self) -> ConceptBlueprint:
        """Convert this ConceptBlueprint to the original core ConceptBlueprint."""
        # TODO: Clarify concept structure blueprint
        converted_structure: str | dict[str, str | ConceptStructureBlueprint] | None = None
        if self.structure:
            converted_structure = {}
            for field_name, field_spec in self.structure.items():
                converted_structure[field_name] = field_spec.to_blueprint()

        return ConceptBlueprint(description=self.description, structure=converted_structure, refines=self.refines)

    def _format_type_display(self, field_spec: ConceptStructureSpec) -> str:
        """Format the type display string for a field, including extra info for complex types."""
        match field_spec.type:
            case ConceptStructureSpecFieldType.CONCEPT:
                return f"concept[{field_spec.concept_ref}]"
            case ConceptStructureSpecFieldType.LIST:
                if field_spec.item_type == "concept":
                    return f"list[concept[{field_spec.item_concept_ref}]]"
                return f"list[{field_spec.item_type}]"
            case (
                ConceptStructureSpecFieldType.TEXT
                | ConceptStructureSpecFieldType.INTEGER
                | ConceptStructureSpecFieldType.BOOLEAN
                | ConceptStructureSpecFieldType.NUMBER
                | ConceptStructureSpecFieldType.DATE
            ):
                return field_spec.type

    @override
    def rendered_pretty(self, *, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        concept_group = Group()
        if title:
            concept_group.renderables.append(Text(title, style="bold"))
        concept_group.renderables.append(Text.from_markup(f"Concept: [green]{self.concept_code}[/green]", style="bold"))
        if self.refines:
            concept_group.renderables.append(Text.from_markup(f"Refines: [green]{self.refines}[/green]"))
        concept_group.renderables.append(Text.from_markup(f"\nDescription: [yellow italic]{self.description}[/yellow italic]\n"))
        if self.structure:
            # Check if any field has a default value
            has_default_values = any(field_spec.default_value is not None for field_spec in self.structure.values())

            structure_table = Table(
                title="Structure:",
                title_style="not italic",
                title_justify="left",
                show_header=True,
                header_style="dim",
                show_edge=True,
                show_lines=True,
                border_style="dim",
            )
            structure_table.add_column("Field", style="blue")
            structure_table.add_column("Description", style="white italic")
            structure_table.add_column("Type", style="white")
            structure_table.add_column("Required", style="white")
            if has_default_values:
                structure_table.add_column("Default Value", style="white")

            for field_name, field_spec in self.structure.items():
                required_text = "Yes" if field_spec.required else "No"
                type_display = self._format_type_display(field_spec)
                row_data = [field_name, field_spec.description, type_display, required_text]
                if has_default_values:
                    row_data.append(str(field_spec.default_value) if field_spec.default_value is not None else "")
                structure_table.add_row(*row_data)
            concept_group.renderables.append(structure_table)

        return concept_group
