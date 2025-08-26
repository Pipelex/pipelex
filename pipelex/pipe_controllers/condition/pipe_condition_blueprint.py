from typing import Dict, Literal, Optional

from pydantic import Field, RootModel

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint

PipeConditionPipeMapRoot = Dict[str, str]


class PipeConditionPipeMapBlueprint(RootModel[PipeConditionPipeMapRoot]):
    root: PipeConditionPipeMapRoot = Field(default_factory=dict)


class PipeConditionBlueprint(PipeBlueprint):
    type: Literal["PipeCondition"] = "PipeCondition"
    expression_template: Optional[str] = None
    expression: Optional[str] = None
    pipe_map: PipeConditionPipeMapBlueprint = Field(default_factory=PipeConditionPipeMapBlueprint)
    default_pipe_code: Optional[str] = None
    add_alias_from_expression_to: Optional[str] = None
