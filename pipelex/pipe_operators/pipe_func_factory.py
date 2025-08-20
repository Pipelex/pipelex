from typing_extensions import override

from pipelex.core.pipe.pipe_blueprint import PipeBlueprint
from pipelex.core.pipe.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipe.pipe_input_spec import PipeInputSpec
from pipelex.pipe_operators.pipe_func import PipeFunc


class PipeFuncBlueprint(PipeBlueprint):
    function_name: str


class PipeFuncFactory(PipeFactoryProtocol[PipeFuncBlueprint, PipeFunc]):
    @classmethod
    @override
    def make_pipe_from_blueprint(
        cls,
        domain_code: str,
        pipe_code: str,
        pipe_blueprint: PipeFuncBlueprint,
    ) -> PipeFunc:
        return PipeFunc(
            domain=domain_code,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            inputs=PipeInputSpec.make_from_blueprint(blueprint=pipe_blueprint.inputs or {}),
            output_concept_code=pipe_blueprint.output,
            function_name=pipe_blueprint.function_name,
        )
