from typing import Literal

from pydantic import Field

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint


class PipeFuncBlueprint(PipeBlueprint):
    type: Literal["PipeFunc"] = "PipeFunc"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"
    function_name: str = Field(description="The name of the function to call.")
