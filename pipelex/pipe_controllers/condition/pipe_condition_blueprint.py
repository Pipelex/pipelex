from typing import Literal

from pydantic import Field, RootModel

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint

PipeConditionPipeMapRoot = dict[str, str]


class PipeConditionPipeMapBlueprint(RootModel[PipeConditionPipeMapRoot]):
    root: PipeConditionPipeMapRoot = Field(default_factory=dict)


class PipeConditionBlueprint(PipeBlueprint):
    type: Literal["PipeCondition"] = "PipeCondition"
    category: Literal["PipeController"] = "PipeController"
    expression_template: str | None = None
    expression: str | None = None
    pipe_map: PipeConditionPipeMapBlueprint = Field(default_factory=PipeConditionPipeMapBlueprint)
    default_pipe_code: str | None = None
    add_alias_from_expression_to: str | None = None
