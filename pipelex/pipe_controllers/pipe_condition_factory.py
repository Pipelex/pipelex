from typing import Dict, Optional

from typing_extensions import override

from pipelex.core.pipe.pipe_blueprint import PipeBlueprint
from pipelex.core.pipe.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipe.pipe_input_spec import PipeInputSpec
from pipelex.pipe_controllers.pipe_condition import PipeCondition


class PipeConditionBlueprint(PipeBlueprint):
    expression_template: Optional[str] = None
    expression: Optional[str] = None
    # TODO: make the values of pipe_map a Union[str, PipeAdapter] or something to set a specific alias
    pipe_map: Dict[str, str]
    default_pipe_code: Optional[str] = None
    add_alias_from_expression_to: Optional[str] = None


class PipeConditionFactory(PipeFactoryProtocol[PipeConditionBlueprint, PipeCondition]):
    @classmethod
    @override
    def make_pipe_from_blueprint(
        cls,
        domain_code: str,
        pipe_code: str,
        pipe_blueprint: PipeConditionBlueprint,
    ) -> PipeCondition:
        return PipeCondition(
            domain=domain_code,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            inputs=PipeInputSpec.make_from_blueprint(blueprint=pipe_blueprint.inputs or {}),
            output_concept_code=pipe_blueprint.output,
            expression_template=pipe_blueprint.expression_template,
            expression=pipe_blueprint.expression,
            pipe_map=pipe_blueprint.pipe_map,
            default_pipe_code=pipe_blueprint.default_pipe_code,
            add_alias_from_expression_to=pipe_blueprint.add_alias_from_expression_to,
        )
