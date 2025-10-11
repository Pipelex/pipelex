from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.pipes.exceptions import PipeBlueprintError
from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.tools.misc.string_utils import is_snake_case
from pipelex.types import StrEnum


class AllowedPipeCategories(StrEnum):
    PIPE_OPERATOR = "PipeOperator"
    PIPE_CONTROLLER = "PipeController"

    @classmethod
    def value_list(cls) -> list[str]:
        return list(cls)

    @property
    def is_controller(self) -> bool:
        match self:
            case AllowedPipeCategories.PIPE_CONTROLLER:
                return True
            case AllowedPipeCategories.PIPE_OPERATOR:
                return False

    @classmethod
    def is_controller_by_str(cls, category_str: str) -> bool:
        try:
            category = cls(category_str)
            return category.is_controller
        except ValueError:
            return False


class AllowedPipeTypes(StrEnum):
    # Pipe Operators
    PIPE_FUNC = "PipeFunc"
    PIPE_IMG_GEN = "PipeImgGen"
    PIPE_COMPOSE = "PipeCompose"
    PIPE_LLM = "PipeLLM"
    PIPE_OCR = "PipeOcr"
    # Pipe Controller
    PIPE_BATCH = "PipeBatch"
    PIPE_CONDITION = "PipeCondition"
    PIPE_PARALLEL = "PipeParallel"
    PIPE_SEQUENCE = "PipeSequence"

    @classmethod
    def value_list(cls) -> list[str]:
        return list(cls)


class PipeBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str | None = None
    category: Any
    type: Any  # TODO: Find a better way to handle this.
    description: str | None = None
    inputs: dict[str, str | InputRequirementBlueprint] | None = None
    output: str

    @field_validator("type", mode="after")
    @staticmethod
    def validate_pipe_type(value: Any) -> Any:
        """Validate that the pipe type is one of the allowed values."""
        if value not in AllowedPipeTypes.value_list():
            msg = f"Invalid pipe type '{value}'. Must be one of: {AllowedPipeTypes.value_list()}"
            raise PipeBlueprintError(msg)
        return value

    @field_validator("category", mode="after")
    @staticmethod
    def validate_pipe_category(value: Any) -> Any:
        """Validate that the pipe category is one of the allowed values."""
        if value not in AllowedPipeCategories.value_list():
            msg = f"Invalid pipe category '{value}'. Must be one of: {AllowedPipeCategories.value_list()}"
            raise PipeBlueprintError(msg)
        return value

    @field_validator("output", mode="before")
    @staticmethod
    def validate_concept_string_or_code(output: str) -> str:
        ConceptBlueprint.validate_concept_string_or_code(concept_string_or_code=output)
        return output

    @classmethod
    def validate_pipe_code_syntax(cls, pipe_code: str) -> str:
        if not is_snake_case(pipe_code):
            msg = f"Invalid pipe code syntax '{pipe_code}'. Must be in snake_case."
            raise PipeBlueprintError(msg)
        return pipe_code
