from typing import Any, Dict, Optional

from pydantic import BaseModel, model_validator
from typing_extensions import Self

from pipelex.core.pipes.pipe_input_spec import InputRequirementBlueprint
from pipelex.types import StrEnum


class PipeBlueprintError(Exception):
    """Exception raised for errors in the PipeBlueprint class."""

    pass


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
    inputs: Optional[Dict[str, InputRequirementBlueprint]] = None
    output: str

    @model_validator(mode="after")
    def validate_pipe_type(self) -> Self:
        """Validate that the pipe type is one of the allowed values."""
        allowed_types = [_type.value for _type in AllowedPipeTypes]
        if self.type not in allowed_types:
            raise PipeBlueprintError(f"Invalid pipe type '{self.type}'. Must be one of: {sorted(allowed_types)}")
        return self
