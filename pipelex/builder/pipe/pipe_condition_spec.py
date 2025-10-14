from typing import Literal

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema
from typing_extensions import override

from pipelex.builder.pipe.pipe_signature import PipeSpec
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome


class PipeConditionSpec(PipeSpec):
    """PipeConditionSpec enables branching logic in pipelines by evaluating expressions
    and executing different pipes based on the results.

    Validation Rules:
        1. Either expression or expression_template should be provided, not both.
        2. outcomes map keys, must be strings representing possible valmes from expression.
        3. All values in outcomes map and default_outcome must be either valid pipe_code references or special outcomes "fail" or "continue".

    """

    type: SkipJsonSchema[Literal["PipeCondition"]] = "PipeCondition"
    pipe_category: SkipJsonSchema[Literal["PipeController"]] = "PipeController"
    jinja2_expression_template: str = Field(description="Jinja2 expression to evaluate.")
    outcomes: dict[str, str] = Field(..., description="Mapping `dict[str, str]` of condition to outcomes.")
    default_outcome: str | SpecialOutcome = Field(description="The fallback outcome if the expression result does not match any key in outcome map.")

    @override
    def to_blueprint(self) -> PipeConditionBlueprint:
        base_blueprint = super().to_blueprint()
        return PipeConditionBlueprint(
            description=base_blueprint.description,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            type=self.type,
            pipe_category=self.pipe_category,
            expression_template=self.jinja2_expression_template,
            expression=None,
            outcomes=self.outcomes,
            default_outcome=self.default_outcome,
            add_alias_from_expression_to=None,
        )
