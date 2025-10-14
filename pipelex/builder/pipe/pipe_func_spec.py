from typing import Literal

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema
from typing_extensions import override

from pipelex.builder.pipe.pipe_signature import PipeSpec
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint


class PipeFuncSpec(PipeSpec):
    """PipeFunc enables calling custom functions in the Pipelex framework."""

    type: SkipJsonSchema[Literal["PipeFunc"]] = "PipeFunc"
    pipe_category: SkipJsonSchema[Literal["PipeOperator"]] = "PipeOperator"
    function_name: str = Field(description="The name of the function to call.")

    @override
    def to_blueprint(self) -> PipeFuncBlueprint:
        base_blueprint = super().to_blueprint()
        return PipeFuncBlueprint(
            description=base_blueprint.description,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            type=self.type,
            pipe_category=self.pipe_category,
            function_name=self.function_name,
        )
