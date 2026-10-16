from typing import Any

from typing_extensions import override

from pipelex.core.method_trees.building_bundle import get_building_tree_bundle
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.pipe_machinery.pipe_factory import PipeFactoryProtocol
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint


class PipeFuncFactory(PipeFactoryProtocol[PipeFuncBlueprint, PipeFunc]):
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
        blueprint: PipeFuncBlueprint,
    ) -> PipeFunc:
        pipe_func = PipeFunc(
            domain_code=domain_code,
            code=pipe_code,
            description=description,
            inputs=inputs,
            output=output,
            function_name=blueprint.function_name,
        )
        # The function's import path resolves from the root of the method tree the bundle was read in, recorded here
        # without reading anything: the module is located and checked when the library validates the step.
        pipe_func.place_in_tree(tree_bundle=get_building_tree_bundle())
        return pipe_func
