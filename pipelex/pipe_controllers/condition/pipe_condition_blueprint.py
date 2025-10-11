from typing import Literal

from pydantic import Field

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint


class PipeConditionBlueprint(PipeBlueprint):
    type: Literal["PipeCondition"] = "PipeCondition"
    category: Literal["PipeController"] = "PipeController"
    expression_template: str | None = None
    expression: str | None = None
    pipe_map: dict[str, str] = Field(default_factory=dict)
    default_pipe_code: str | None = None
    add_alias_from_expression_to: str | None = None
