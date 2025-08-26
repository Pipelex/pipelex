from typing import List, Literal, Optional

from pydantic import field_validator

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class PipeParallelBlueprint(PipeBlueprint):
    type: Literal["PipeParallel"] = "PipeParallel"
    parallels: List[SubPipeBlueprint]
    add_each_output: bool = True
    combined_output: Optional[str] = None

    @field_validator("combined_output", mode="before")
    def validate_combined_output(cls, combined_output: str) -> str:
        if combined_output:
            ConceptBlueprint.validate_concept_string_or_concept_code(concept_string_or_concept_code=combined_output)
        return combined_output
