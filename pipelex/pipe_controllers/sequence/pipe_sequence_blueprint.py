from typing import List, Literal

from pydantic import Field

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class PipeSequenceBlueprint(PipeBlueprint):
    """PipeSequence is used to run a list of pipes in sequence."""

    type: Literal["PipeSequence"] = "PipeSequence"
    steps: List[SubPipeBlueprint] = Field(description="The list of pipe steps to run in sequence.")
