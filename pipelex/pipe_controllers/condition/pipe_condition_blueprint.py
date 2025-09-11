from typing import Dict, Literal, Optional

from pydantic import Field, RootModel

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint

PipeConditionPipeMapRoot = Dict[str, str]


class PipeConditionPipeMapBlueprint(RootModel[PipeConditionPipeMapRoot]):
    """Blueprint for condition-to-pipe mapping in PipeCondition.

    Maps condition values to pipe codes for conditional execution.

    Attributes:
        root: Dictionary mapping condition results (keys) to pipe codes (values).
              Each key represents a possible condition outcome, and its value
              is the pipe code to execute when that condition is met.
    """

    root: PipeConditionPipeMapRoot = Field(default_factory=dict)


class PipeConditionBlueprint(PipeBlueprint):
    type: Literal["PipeCondition"] = "PipeCondition"
    category: Literal["PipeController"] = "PipeController"
    expression_template: Optional[str] = None
    expression: Optional[str] = None
    pipe_map: PipeConditionPipeMapBlueprint = Field(default_factory=PipeConditionPipeMapBlueprint)
    default_pipe_code: Optional[str] = None
    add_alias_from_expression_to: Optional[str] = None
