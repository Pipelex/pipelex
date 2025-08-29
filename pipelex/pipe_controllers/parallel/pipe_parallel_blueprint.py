from typing import List, Literal, Optional

from pydantic import Field, field_validator

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class PipeParallelBlueprint(PipeBlueprint):
    """PipeParallel is used to run multiple different pipes in parallel."""

    type: Literal["PipeParallel"] = "PipeParallel"
    parallels: List[SubPipeBlueprint] = Field(description="The list of pipe steps to run in parallel.")
    add_each_output: bool = Field(default=True, description="Whether to add each output to the combined output.")
    combined_output: Optional[str] = Field(default=None, description="The name of the combined output.")

    @field_validator("combined_output", mode="before")
    def validate_combined_output(cls, combined_output: str) -> str:
        if combined_output:
            ConceptBlueprint.validate_concept_string_or_concept_code(concept_string_or_concept_code=combined_output)
        return combined_output
