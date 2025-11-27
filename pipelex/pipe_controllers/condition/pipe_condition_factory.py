from typing import Any

from typing_extensions import override

from pipelex.core.concepts.concept import Concept
from pipelex.core.pipes.inputs.input_requirements import InputRequirements
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.pipe_controllers.condition.exceptions import PipeConditionFactoryError
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint


class PipeConditionFactory(PipeFactoryProtocol[PipeConditionBlueprint, PipeCondition]):
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
        blueprint: PipeConditionBlueprint,
    ) -> PipeCondition:
        # Compute expression from expression_template or expression in blueprint
        expression: str | None = None
        if blueprint.expression_template:
            expression = blueprint.expression_template
        elif blueprint.expression:
            expression = "{{ " + blueprint.expression + " }}"
        else:
            msg = "PipeCondition must have either expression_template or expression"
            raise PipeConditionFactoryError(msg)

        return PipeCondition(
            domain=domain_code,
            code=pipe_code,
            description=description,
            inputs=inputs,
            output=output,
            expression=expression,
            outcome_map=blueprint.outcomes,
            default_outcome=blueprint.default_outcome,
            add_alias_from_expression_to=blueprint.add_alias_from_expression_to,
        )
