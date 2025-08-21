from typing import List, Literal, Optional

from typing_extensions import override

from pipelex.core.concepts.concept import Concept
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.pipe_input_spec import PipeInputSpec
from pipelex.exceptions import PipeDefinitionError
from pipelex.pipe_controllers.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipe_controllers.sub_pipe_factory import SubPipeBlueprint


class PipeParallelBlueprint(PipeBlueprint):
    type: Literal["PipeParallel"] = "PipeParallel"
    parallels: List[SubPipeBlueprint]
    add_each_output: bool = True
    combined_output: Optional[str] = None


class PipeParallelFactory(PipeFactoryProtocol[PipeParallelBlueprint, PipeParallel]):
    @classmethod
    @override
    def make_pipe_from_blueprint(
        cls,
        domain_code: str,
        pipe_code: str,
        pipe_blueprint: PipeParallelBlueprint,
    ) -> PipeParallel:
        parallel_sub_pipes: List[SubPipe] = []
        for sub_pipe_blueprint in pipe_blueprint.parallels:
            if not sub_pipe_blueprint.result:
                raise PipeDefinitionError("PipeParallel requires a result specified for each parallel sub pipe")
            sub_pipe = sub_pipe_blueprint.make_sub_pipe()
            parallel_sub_pipes.append(sub_pipe)
        if not pipe_blueprint.add_each_output and not pipe_blueprint.combined_output:
            raise PipeDefinitionError("PipeParallel requires either add_each_output or combined_output to be set")

        return PipeParallel(
            domain=domain_code,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            inputs=PipeInputSpec.make_from_blueprint(domain=domain_code, blueprint=pipe_blueprint.inputs or {}),
            output=Concept(
                code=pipe_blueprint.output, domain=domain_code, definition=pipe_blueprint.output, structure_class_name=pipe_blueprint.output
            ),
            parallel_sub_pipes=parallel_sub_pipes,
            add_each_output=pipe_blueprint.add_each_output,
            combined_output=pipe_blueprint.combined_output,
        )
