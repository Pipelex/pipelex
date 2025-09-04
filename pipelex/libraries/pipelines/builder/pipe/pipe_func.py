from typing import Literal

from pydantic import Field

from pipelex.libraries.pipelines.builder.pipe.pipe import PipeBlueprint


class PipeFuncBlueprint(PipeBlueprint):
    type: Literal["PipeFunc"] = "PipeFunc"
    function_name: str = Field(description="The name of the function to call.")


class PipeFuncSpecBlueprint(PipeFuncBlueprint):
    the_pipe_code: str = Field(description="Pipe code. Must be snake_case.")
