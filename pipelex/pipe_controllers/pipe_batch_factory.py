from typing import Any, Dict, Optional

from typing_extensions import override

from pipelex.core.pipe_blueprint import PipeBlueprint, PipeSpecificFactoryProtocol
from pipelex.core.pipe_input_spec import PipeInputSpec
from pipelex.core.pipe_run_params import BatchParams
from pipelex.pipe_controllers.pipe_batch import PipeBatch


class PipeBatchBlueprint(PipeBlueprint):
    branch_pipe_code: str

    input_list_name: Optional[str] = None
    input_item_name: Optional[str] = None


class PipeBatchFactory(PipeSpecificFactoryProtocol[PipeBatchBlueprint, PipeBatch]):
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
            inputs=PipeInputSpec(root=pipe_blueprint.inputs or {}),
            output_concept_code=pipe_blueprint.output,
            branch_pipe_code=pipe_blueprint.branch_pipe_code,
            batch_params=batch_params,
        )

    @classmethod
    @override
    def make_pipe_from_details_dict(
        cls,
        domain_code: str,
        pipe_code: str,
        details_dict: Dict[str, Any],
    ) -> PipeBatch:
        pipe_blueprint = PipeBatchBlueprint.model_validate(details_dict)
        return cls.make_pipe_from_blueprint(
            domain_code=domain_code,
            pipe_code=pipe_code,
            pipe_blueprint=pipe_blueprint,
        )
