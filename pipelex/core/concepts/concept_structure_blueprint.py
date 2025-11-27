from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from pipelex.pipe_run.pipe_run_params import PipeRunParamKey
from pipelex.types import Self, StrEnum

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
            raise ValueError(msg)

        # If type is "dict", key_type and value_type must not be empty
        if self.type == ConceptStructureBlueprintFieldType.DICT:
            if not self.key_type:
                msg = f"When type is '{ConceptStructureBlueprintFieldType.DICT}', key_type must not be empty. Actual key_type: {self.key_type}"
                raise ValueError(msg)
            if not self.value_type:
                msg = f"When type is '{ConceptStructureBlueprintFieldType.DICT}', value_type must not be empty. Actual value_type: {self.value_type}"
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
        raise ValueError(msg)
