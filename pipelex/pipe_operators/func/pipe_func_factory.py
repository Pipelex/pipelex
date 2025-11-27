from typing import Any

from typing_extensions import override

from pipelex.core.concepts.concept import Concept
from pipelex.core.pipes.inputs.input_requirements import InputRequirements
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint


class PipeFuncFactory(PipeFactoryProtocol[PipeFuncBlueprint, PipeFunc]):
    @classmethod
    @override
    def make(
        cls,
        pipe_category: Any,
        pipe_type: str,
        pipe_code: str,
        domain_code: str,
        description: str | None,
        inputs: InputRequirements,
        output: Concept,
        blueprint: PipeFuncBlueprint,
    ) -> PipeFunc:
        # TODO: make function_name into a callable in PipeFunc
        return PipeFunc(
            domain=domain_code,
            code=pipe_code,
            description=description,
            inputs=inputs,
            output=output,
            function_name=blueprint.function_name,
        )
