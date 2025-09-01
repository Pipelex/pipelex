from typing import List, Literal

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class PipeSequenceBlueprint(PipeBlueprint):
    """Blueprint for sequential pipe execution in the Pipelex framework.

    PipeSequence orchestrates the execution of multiple pipes in a defined order,
    where each pipe's output can be used as input for subsequent pipes. This enables
    building complex data processing workflows with step-by-step transformations.

    Attributes:
        type: Fixed to "PipeSequence" for this pipe type.
        steps: Ordered list of SubPipeBlueprint instances defining the pipes
              to execute. Each step runs after the previous one completes,
              with access to all prior outputs in the context.

    Validation Rules:
        1. Steps list must not be empty.
        2. Each step must be a valid SubPipeBlueprint instance.
        3. Pipe codes referenced in steps must exist in the pipeline.

    Raises:
        PipeDefinitionError: When validation rules are violated.
    """

    type: Literal["PipeSequence"] = "PipeSequence"
    steps: List[SubPipeBlueprint]
