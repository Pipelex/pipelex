from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, Field, field_validator

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.pipes.exceptions import PipeBlueprintError
from pipelex.core.pipes.pipe_input_spec_blueprint import InputRequirementBlueprint
from pipelex.tools.misc.string_utils import is_snake_case
from pipelex.types import StrEnum


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


class PipeBlueprint(BaseModel):
    """Simple data container for pipe blueprint information.

    The 'type' field uses Any to avoid type override conflicts but is validated
    at runtime to ensure only valid pipe type values are allowed.
    """

    type: Any  # TODO: Find a better way to handle this.
    definition: Optional[str] = None
    inputs: Optional[Dict[str, Union[str, InputRequirementBlueprint]]] = None
    output_concept_string_or_concept_code: str = Field(alias="output")

    @field_validator("type", mode="after")
    def validate_pipe_type(cls, value: Any) -> Any:
        """Validate that the pipe type is one of the allowed values."""
        allowed_types = [_type.value for _type in AllowedPipeTypes]
        if value not in allowed_types:
            raise PipeBlueprintError(f"Invalid pipe type '{value}'. Must be one of: {allowed_types}")
        return value

    @field_validator("output_concept_string_or_concept_code", mode="before")
    def validate_concept_string_or_concept_code(cls, output: str) -> str:
        ConceptBlueprint.validate_concept_string_or_concept_code(concept_string_or_concept_code=output)
        return output

    @classmethod
    def validate_pipe_code_syntax(cls, pipe_code: str) -> str:
        if not is_snake_case(pipe_code):
            raise PipeBlueprintError(f"Invalid pipe code syntax '{pipe_code}'. Must be in snake_case.")
        return pipe_code
