from typing import Literal

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint


class PipeFuncBlueprint(PipeBlueprint):
    type: Literal["PipeFunc"] = "PipeFunc"
    function_name: str
