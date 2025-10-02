from typing import Literal

from pydantic import Field
from typing_extensions import override

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.core.pipes.specific_pipe import SpecificPipeCodesEnum


class PipeConditionBlueprint(PipeBlueprint):
    type: Literal["PipeCondition"] = "PipeCondition"
    category: Literal["PipeController"] = "PipeController"
    expression_template: str | None = None
    expression: str | None = None
    pipe_map: dict[str, str] = Field(default_factory=dict)
    default_pipe_code: str | None = None
    add_alias_from_expression_to: str | None = None

    @property
    @override
    def pipe_dependencies(self) -> set[str]:
        """Return the set of pipe codes from pipe_map and default_pipe_code.

        Excludes special pipe codes like 'continue'.
        """
        codes = set(self.pipe_map.values())
        if self.default_pipe_code:
            codes.add(self.default_pipe_code)
        return codes - set(SpecificPipeCodesEnum.value_list())
