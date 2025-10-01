from typing import Literal

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema
from typing_extensions import override

from pipelex.libraries.pipelines.builder.pipe.pipe_signature import PipeSpec
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint


class PipeConditionSpec(PipeSpec):
    """PipeConditionSpec enables branching logic in pipelines by evaluating expressions
    and executing different pipes based on the results.

    Validation Rules:
        1. Either expression or expression_template should be provided, not both.
        2. pipe_map keys must be strings representing possible condition outcomes.
        3. All pipe codes in pipe_map and default_pipe_code must be valid pipe references.

    """

    type: SkipJsonSchema[Literal["PipeCondition"]] = "PipeCondition"
    category: SkipJsonSchema[Literal["PipeController"]] = "PipeController"
    the_pipe_code: str = Field(description="Pipe code. Must be snake_case.")
    jinja2_expression_template: str = Field(description="Jinja2 expression to evaluate.")
    pipe_map: dict[str, str] = Field(..., description="Mapping `dict[str, str]` of condition results to pipe codes.")
    default_pipe_code: str | None = Field(
        default=None, description="The fallback pipe code to execute if the expression result does not match any key in pipe_map."
    )

    @override
    def to_blueprint(self) -> PipeConditionBlueprint:
        base_blueprint = super().to_blueprint()
        return PipeConditionBlueprint(
            description=base_blueprint.description,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            type=self.type,
            category=self.category,
            expression_template=self.jinja2_expression_template,
            expression=None,
            pipe_map=self.pipe_map,
            default_pipe_code=self.default_pipe_code,
            add_alias_from_expression_to=None,
        )
