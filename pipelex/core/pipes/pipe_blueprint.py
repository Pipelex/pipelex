from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, field_validator

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.pipes.exceptions import PipeBlueprintError
from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.tools.misc.string_utils import is_snake_case
from pipelex.types import StrEnum


class AllowedPipeCategories(StrEnum):
    PIPE_OPERATOR = "PipeOperator"
    PIPE_CONTROLLER = "PipeController"

    @classmethod
    def value_list(cls) -> List[str]:
        return [value for value in cls]


class AllowedPipeTypes(StrEnum):
    # Pipe Operators
    PIPE_FUNC = "PipeFunc"
    PIPE_IMG_GEN = "PipeImgGen"
    PIPE_JINJA2 = "PipeJinja2"
    PIPE_LLM = "PipeLLM"
    PIPE_OCR = "PipeOcr"
    # Pipe Controller
    PIPE_BATCH = "PipeBatch"
    PIPE_CONDITION = "PipeCondition"
    PIPE_PARALLEL = "PipeParallel"
    PIPE_SEQUENCE = "PipeSequence"

    @classmethod
    def value_list(cls) -> List[str]:
        return [value for value in cls]


class PipeBlueprint(BaseModel):
    category: Any
    type: Any  # TODO: Find a better way to handle this.
    definition: Optional[str] = None
    inputs: Optional[Dict[str, Union[str, InputRequirementBlueprint]]] = None
    output: str

    @field_validator("type", mode="after")
    def validate_pipe_type(cls, value: Any) -> Any:
        """Validate that the pipe type is one of the allowed values."""
        if value not in AllowedPipeTypes.value_list():
            raise PipeBlueprintError(f"Invalid pipe type '{value}'. Must be one of: {AllowedPipeTypes.value_list()}")
        return value

    @field_validator("category", mode="after")
    def validate_pipe_category(cls, value: Any) -> Any:
        """Validate that the pipe category is one of the allowed values."""
        if value not in AllowedPipeCategories.value_list():
            raise PipeBlueprintError(f"Invalid pipe category '{value}'. Must be one of: {AllowedPipeCategories.value_list()}")
        return value

    @field_validator("output", mode="before")
    def validate_concept_string_or_concept_code(cls, output: str) -> str:
        ConceptBlueprint.validate_concept_string_or_concept_code(concept_string_or_code=output)
        return output

    @classmethod
    def validate_pipe_code_syntax(cls, pipe_code: str) -> str:
        if not is_snake_case(pipe_code):
            raise PipeBlueprintError(f"Invalid pipe code syntax '{pipe_code}'. Must be in snake_case.")
        return pipe_code
