from typing import Any, Dict, Optional

from pydantic import BaseModel, model_validator
from typing_extensions import Self

from pipelex.core.pipe.pipe_input_spec import InputRequirementBlueprint


class PipeBlueprint(BaseModel):
    """Simple data container for pipe blueprint information.

    The 'type' field uses Any to avoid type override conflicts but is validated
    at runtime to ensure only valid pipe type values are allowed.
    """

    type: Any
    definition: Optional[str] = None
    inputs: Optional[Dict[str, InputRequirementBlueprint]] = None
    output: str

    @model_validator(mode="after")
    def validate_pipe_type(self) -> Self:
        """Validate that the pipe type is one of the allowed values."""
        allowed_types = {
            "PipeFunc",
            "PipeImgGen",
            "PipeJinja2",
            "PipeLLM",
            "PipeOcr",
            "PipeBatch",
            "PipeCondition",
            "PipeParallel",
            "PipeSequence",
        }
        if self.type not in allowed_types:
            raise ValueError(f"Invalid pipe type '{self.type}'. Must be one of: {sorted(allowed_types)}")
        return self
