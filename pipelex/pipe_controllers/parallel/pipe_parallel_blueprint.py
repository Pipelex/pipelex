from typing import List, Literal, Optional

from pydantic import field_validator

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class PipeParallelBlueprint(PipeBlueprint):
    """Blueprint for parallel pipe execution in the Pipelex framework.

    PipeParallel enables concurrent execution of multiple pipes, improving performance
    for independent operations. All parallel pipes receive the same input context
    and their outputs can be combined or kept separate.

    Attributes:
        type: Fixed to "PipeParallel" for this pipe type.
        parallels: List of SubPipeBlueprint instances to execute concurrently.
                  All pipes run simultaneously with access to the same input context.
        add_each_output: Whether to include individual pipe outputs in the combined
                        result. Default is True. When False, only combined_output is used.
        combined_output: Optional concept string/code for the combined output structure.
                        When specified, all parallel outputs are merged into this concept.

    Validation Rules:
        1. Parallels list must not be empty.
        2. Each parallel step must be a valid SubPipeBlueprint.
        3. combined_output, when specified, must be a valid concept string or code.
        4. Pipe codes in parallels must reference existing pipes.

    Raises:
        PipeDefinitionError: When validation rules are violated.
    """

    type: Literal["PipeParallel"] = "PipeParallel"
    parallels: List[SubPipeBlueprint]
    add_each_output: bool = True
    combined_output: Optional[str] = None

    @field_validator("combined_output", mode="before")
    def validate_combined_output(cls, combined_output: str) -> str:
        if combined_output:
            ConceptBlueprint.validate_concept_string_or_concept_code(concept_string_or_concept_code=combined_output)
        return combined_output
