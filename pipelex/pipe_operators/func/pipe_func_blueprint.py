from typing import Literal

from pydantic import Field
from typing_extensions import override

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint


class PipeFuncBlueprint(PipeBlueprint):
    type: Literal["PipeFunc"] = "PipeFunc"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"
    function_name: str = Field(description="The name of the function to call.")

    @override
    def validate_inputs(self):
        pass

    @override
    def validate_output(self):
        pass
