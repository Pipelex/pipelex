from typing import Literal

from pydantic import Field
from typing_extensions import override

from pipelex.libraries.pipelines.builder.pipe.pipe_signature import PipeSpec
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint


class PipeFuncSpec(PipeSpec):
    """PipeFunc enables calling custom functions in the Pipelex framework.

    Attributes:
        the_pipe_code: Pipe code. Must be snake_case.
        type: Fixed to "PipeFunc" for this pipe type.
        category: Fixed to "PipeOperator" for this pipe category.
        function_name: The name of the function to call.

    """

    type: Literal["PipeFunc"] = "PipeFunc"
    category: Literal["PipeOperator"] = "PipeOperator"
    the_pipe_code: str = Field(description="Pipe code. Must be snake_case.")
    function_name: str = Field(description="The name of the function to call.")

    @override
    def to_blueprint(self) -> PipeFuncBlueprint:
        base_blueprint = super().to_blueprint()
        return PipeFuncBlueprint(
            definition=base_blueprint.definition,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            type=self.type,
            category=self.category,
            function_name=self.function_name,
        )
