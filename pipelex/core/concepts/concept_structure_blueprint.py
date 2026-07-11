from datetime import date, datetime, time
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from pipelex.core.concepts.validation import is_concept_ref_or_code_valid
from pipelex.pipe_run.pipe_run_params import PipeRunParamKey

# Reserved field names that cannot be used in concept structures
# These are either Pydantic BaseModel reserved attributes or internal metadata fields
RESERVED_FIELD_NAMES = frozenset(
    [
        # Pipe run parameter keys (from PipeRunParamKey enum)
        *PipeRunParamKey.value_list(),
        # Pydantic BaseModel reserved attributes
        "model_config",
        "model_fields",
        "model_computed_fields",
        "model_dump",
        "model_dump_json",
        "model_validate",
        "model_validate_json",
        "model_copy",
        "model_fields_set",
        "model_extra",
        # Internal metadata fields (with underscore prefix)
        "_stuff_name",
        "_content_class",
        "_concept_code",
        "_stuff_code",
        "_content",
    ]
)


class ConceptStructureBlueprintFieldType(StrEnum):
    TEXT = "text"
    LIST = "list"
    DICT = "dict"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    NUMBER = "number"
    DATE = "date"
    DATETIME = "datetime"
    TIME = "time"
    CONCEPT = "concept"


class ConceptStructureBlueprint(BaseModel):
    description: str
    type: ConceptStructureBlueprintFieldType | None = None
    # type=dict
    key_type: str | None = None
    value_type: str | None = None
    # type=list
    item_type: str | None = None
    # type=concept
    concept_ref: str | None = None
    item_concept_ref: str | None = None

    choices: list[str] | None = Field(default=None)
    default_value: Any | None = None
    required: bool = Field(default=False)

    @field_validator("concept_ref", mode="before")
    @classmethod
    def validate_concept_ref(cls, concept_ref: str | None) -> str | None:
        if concept_ref is not None:
            if not is_concept_ref_or_code_valid(concept_ref_or_code=concept_ref):
                msg = f"Concept ref '{concept_ref}' must be a valid concept ref (domain.ConceptCode) or simply a concept code (PascalCase)"
                raise ValueError(msg)
        return concept_ref

    @field_validator("item_concept_ref", mode="before")
    @classmethod
    def validate_item_concept_ref(cls, item_concept_ref: str | None) -> str | None:
        if item_concept_ref is not None:
            if not is_concept_ref_or_code_valid(concept_ref_or_code=item_concept_ref):
                msg = f"Item concept ref '{item_concept_ref}' must be a valid concept ref (domain.ConceptCode) or simply a concept code (PascalCase)"
                raise ValueError(msg)
        return item_concept_ref

    @model_validator(mode="after")
    def validate_structure_blueprint(self) -> Self:
        """Validate the structure blueprint according to type rules."""
        # If type is None (array), choices must not be None
        if self.type is None and not self.choices:
            msg = f"When type is None (array), choices must not be empty. Actual type: {self.type}, choices: {self.choices}"
            raise ValueError(msg)

        # If type is "dict", key_type and value_type must not be empty
        match self.type:
            case ConceptStructureBlueprintFieldType.DICT:
                if not self.key_type:
                    msg = f"When type is 'dict', key_type must not be empty. Actual key_type: {self.key_type}"
                    raise ValueError(msg)
                if self.key_type not in {"text", "str"}:
                    msg = f"When type is 'dict', key_type must be 'text'. Actual key_type: {self.key_type}"
                    raise ValueError(msg)
                if not self.value_type:
                    msg = f"When type is 'dict', value_type must not be empty. Actual value_type: {self.value_type}"
                    raise ValueError(msg)

            case ConceptStructureBlueprintFieldType.CONCEPT:
                # Validate concept type requires concept_ref
                if not self.concept_ref:
                    msg = "When type is 'concept', concept_ref must be set."
                    raise ValueError(msg)
                # Concept fields cannot have default values
                if self.default_value is not None:
                    msg = "default_value cannot be set for concept type (complex objects cannot have defaults)."
                    raise ValueError(msg)

            case ConceptStructureBlueprintFieldType.LIST:
                # Validate list of concepts requires item_concept_ref
                if self.item_type == "concept" and not self.item_concept_ref:
                    msg = "When item_type is 'concept', item_concept_ref must be set."
                    raise ValueError(msg)
                # item_concept_ref can only be set when item_type is 'concept'
                if self.item_concept_ref and self.item_type != "concept":
                    msg = f"item_concept_ref can only be set when item_type is 'concept'. Actual item_type: {self.item_type}"
                    raise ValueError(msg)

            case (
                ConceptStructureBlueprintFieldType.TEXT
                | ConceptStructureBlueprintFieldType.INTEGER
                | ConceptStructureBlueprintFieldType.BOOLEAN
                | ConceptStructureBlueprintFieldType.NUMBER
                | ConceptStructureBlueprintFieldType.DATE
                | ConceptStructureBlueprintFieldType.DATETIME
                | ConceptStructureBlueprintFieldType.TIME
                | None
            ):
                pass

        # Validate concept_ref can only be set when type is 'concept'
        if self.concept_ref and self.type != ConceptStructureBlueprintFieldType.CONCEPT:
            msg = f"'concept_ref' can only be set when type is 'concept'. Actual type: {self.type}"
            raise ValueError(msg)

        # Check when default_value is not None, type is not None (except for choice fields)
        if self.default_value is not None and self.type is None and not self.choices:
            msg = (
                f"When default_value is not None, type must be specified (unless choices are provided). Actual type: {self.type},"
                f"default_value: {self.default_value}, choices: {self.choices}"
            )
            raise ValueError(msg)

        # Check default_value type is the same as type
        if self.default_value is not None and self.type is not None:
            self._validate_default_value_type()

        # Check default_value is valid for choice fields
        if self.default_value is not None and self.type is None and self.choices:
            if self.default_value not in self.choices:
                msg = f"default_value must be one of the valid choices. Got '{self.default_value}', valid choices: {self.choices}"
                raise ValueError(msg)

        return self

    def _validate_default_value_type(self) -> None:
        if self.type is None or self.default_value is None:
            return

        match self.type:
            case ConceptStructureBlueprintFieldType.TEXT:
                if not isinstance(self.default_value, str):
                    self._raise_type_mismatch_error("str", actual_type_name=type(self.default_value).__name__)
            case ConceptStructureBlueprintFieldType.INTEGER:
                if not isinstance(self.default_value, int):
                    self._raise_type_mismatch_error("int", actual_type_name=type(self.default_value).__name__)
            case ConceptStructureBlueprintFieldType.BOOLEAN:
                if not isinstance(self.default_value, bool):
                    self._raise_type_mismatch_error("bool", actual_type_name=type(self.default_value).__name__)
            case ConceptStructureBlueprintFieldType.NUMBER:
                if not isinstance(self.default_value, (int, float)):
                    self._raise_type_mismatch_error("number (int or float)", actual_type_name=type(self.default_value).__name__)
            case ConceptStructureBlueprintFieldType.LIST:
                if not isinstance(self.default_value, list):
                    self._raise_type_mismatch_error("list", actual_type_name=type(self.default_value).__name__)
            case ConceptStructureBlueprintFieldType.DICT:
                if not isinstance(self.default_value, dict):
                    self._raise_type_mismatch_error("dict", actual_type_name=type(self.default_value).__name__)
            case ConceptStructureBlueprintFieldType.DATE:
                # A calendar date, not a datetime: datetime is a subclass of date, so reject it explicitly
                # (a datetime default would carry a time the `date` field silently drops).
                if not isinstance(self.default_value, date) or isinstance(self.default_value, datetime):
                    self._raise_type_mismatch_error("date", actual_type_name=type(self.default_value).__name__)
            case ConceptStructureBlueprintFieldType.DATETIME:
                if not isinstance(self.default_value, datetime):
                    self._raise_type_mismatch_error("datetime", actual_type_name=type(self.default_value).__name__)
            case ConceptStructureBlueprintFieldType.TIME:
                if not isinstance(self.default_value, time):
                    self._raise_type_mismatch_error("time", actual_type_name=type(self.default_value).__name__)
            case ConceptStructureBlueprintFieldType.CONCEPT:
                # CONCEPT type cannot have default values, this is already validated in validate_structure_blueprint
                # This case is here for exhaustiveness
                pass

    def _raise_type_mismatch_error(self, expected_type_name: str, *, actual_type_name: str) -> None:
        msg = f"default_value type mismatch: expected {expected_type_name} for type '{self.type}', but got {actual_type_name}"
        raise ValueError(msg)
