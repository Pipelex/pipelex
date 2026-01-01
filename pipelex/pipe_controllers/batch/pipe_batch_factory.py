from typing import Any

from typing_extensions import override

from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.pipe_controllers.batch.pipe_batch import PipeBatch
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_run.pipe_run_params import BatchParams


class PipeBatchFactory(PipeFactoryProtocol[PipeBatchBlueprint, PipeBatch]):
    @classmethod
    @override
    def make(
        cls,
        pipe_category: Any,
        pipe_type: str,
        pipe_code: str,
        domain_code: str,
        description: str,
        inputs: InputStuffSpecs,
        output: StuffSpec,
        blueprint: PipeBatchBlueprint,
    ) -> PipeBatch:
        batch_params = BatchParams.make_batch_params(
            input_list_name=blueprint.input_list_name,
            input_item_name=blueprint.input_item_name,
        )
        return PipeBatch(
            domain_code=domain_code,
            code=pipe_code,
            description=description,
            inputs=inputs,
            output=output,
            branch_pipe_code=blueprint.branch_pipe_code,
            batch_params=batch_params,
        )
