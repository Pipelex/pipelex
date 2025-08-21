from typing import Literal, Optional

from typing_extensions import override

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.pipe_input_spec import PipeInputSpec
from pipelex.core.pipes.pipe_run_params import BatchParams
from pipelex.pipe_controllers.pipe_batch import PipeBatch


class PipeBatchBlueprint(PipeBlueprint):
    type: Literal["PipeBatch"] = "PipeBatch"
    branch_pipe_code: str

    input_list_name: Optional[str] = None
    input_item_name: Optional[str] = None


class PipeBatchFactory(PipeFactoryProtocol[PipeBatchBlueprint, PipeBatch]):
    @classmethod
    @override
    def make_pipe_from_blueprint(
        cls,
        domain_code: str,
        pipe_code: str,
        pipe_blueprint: PipeBatchBlueprint,
    ) -> PipeBatch:
        batch_params = BatchParams.make_optional_batch_params(
            input_list_name=pipe_blueprint.input_list_name or False,
            input_item_name=pipe_blueprint.input_item_name,
        )
        return PipeBatch(
            domain=domain_code,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            inputs=PipeInputSpec.make_from_blueprint(domain=domain_code, blueprint=pipe_blueprint.inputs or {}),
            output_concept_code=pipe_blueprint.output,
            branch_pipe_code=pipe_blueprint.branch_pipe_code,
            batch_params=batch_params,
        )
