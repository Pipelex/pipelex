from typing import TYPE_CHECKING, Any

from typing_extensions import override

from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.pipe_controllers.parallel.exceptions import PipeParallelFactoryError
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sub_pipe_factory import SubPipeFactory

if TYPE_CHECKING:
    from pipelex.pipe_controllers.sub_pipe import SubPipe


class PipeParallelFactory(PipeFactoryProtocol[PipeParallelBlueprint, PipeParallel]):
    @classmethod
    @override
    def make(
        cls,
        *,
        pipe_category: Any,
        pipe_type: str,
        pipe_code: str,
        domain_code: str,
        description: str,
        inputs: InputStuffSpecs,
        output: StuffSpec,
        blueprint: PipeParallelBlueprint,
    ) -> PipeParallel:
        parallel_sub_pipes: list[SubPipe] = []
        for sub_pipe_blueprint in blueprint.branches:
            if not sub_pipe_blueprint.result:
                msg = f"Unexpected error in pipe '{pipe_code}': PipeParallel requires a result specified for each parallel sub pipe"
                raise PipeParallelFactoryError(message=msg)
            sub_pipe = SubPipeFactory.make_from_blueprint(sub_pipe_blueprint)
            parallel_sub_pipes.append(sub_pipe)

        return PipeParallel(
            domain_code=domain_code,
            code=pipe_code,
            description=description,
            inputs=inputs,
            output=output,
            parallel_sub_pipes=parallel_sub_pipes,
            add_each_output=blueprint.add_each_output or False,
        )
