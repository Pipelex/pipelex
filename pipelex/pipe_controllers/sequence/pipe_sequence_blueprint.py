from typing import Literal

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class PipeSequenceBlueprint(PipeBlueprint):
    type: Literal["PipeSequence"] = "PipeSequence"
    category: Literal["PipeController"] = "PipeController"
    steps: list[SubPipeBlueprint]
