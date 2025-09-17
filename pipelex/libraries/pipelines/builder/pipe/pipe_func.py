from typing import Literal

from pydantic import Field
from typing_extensions import override

from pipelex.libraries.pipelines.builder.pipe.pipe import PipeBlueprint
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint as PipeFuncBlueprintCore


class PipeFuncBlueprint(PipeBlueprint):
    type: Literal["PipeFunc"] = "PipeFunc"
    category: Literal["PipeOperator"] = "PipeOperator"
    function_name: str = Field(description="The name of the function to call.")

    @override
    def to_core_blueprint(self, pipe_code: str, domain: str) -> PipeFuncBlueprintCore:
        """Convert this PipeFuncBlueprint to the core PipeFuncBlueprint."""

        base_blueprint = super().to_core_blueprint(pipe_code, domain)
        return PipeFuncBlueprintCore(
            definition=base_blueprint.definition,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            type=self.type,
            category=self.category,
            function_name=self.function_name,
        )


class PipeFuncSpecBlueprint(PipeFuncBlueprint):
    the_pipe_code: str = Field(description="Pipe code. Must be snake_case.")
