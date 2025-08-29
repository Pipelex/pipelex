from typing import Dict, Literal, Optional

from pydantic import Field, RootModel

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint

PipeConditionPipeMapRoot = Dict[str, str]


class PipeConditionPipeMapBlueprint(RootModel[PipeConditionPipeMapRoot]):
    root: PipeConditionPipeMapRoot = Field(
        default_factory=dict,
        description="The map of pipes to execute based on the condition. The key is the condition, the value is the pipe code to execute.",
    )


class PipeConditionBlueprint(PipeBlueprint):
    """PipeCondition is used to execute different pipes based on a condition."""

    type: Literal["PipeCondition"] = "PipeCondition"
    expression_template: Optional[str] = Field(default=None, description="The template for the expression to evaluate.")
    expression: Optional[str] = Field(
        default=None, description="The expression to evaluate in order to determine which pipe to execute. (This the result of the previous pipe)"
    )
    pipe_map: PipeConditionPipeMapBlueprint = Field(default_factory=PipeConditionPipeMapBlueprint)
    default_pipe_code: Optional[str] = Field(default=None, description="The pipe to execute if the condition is not met.")
    add_alias_from_expression_to: Optional[str] = Field(default=None, description="The name to use for the expression in the context.")
