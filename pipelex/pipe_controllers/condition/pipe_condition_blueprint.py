from typing import Literal

from pydantic import Field
from typing_extensions import override

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome

OutcomeMap = dict[str, str]


class PipeConditionBlueprint(PipeBlueprint):
    type: Literal["PipeCondition"] = "PipeCondition"
    pipe_category: Literal["PipeController"] = "PipeController"
    expression_template: str | None = None
    expression: str | None = None
    outcomes: OutcomeMap = Field(default_factory=OutcomeMap)
    default_outcome: str | SpecialOutcome
    add_alias_from_expression_to: str | None = None

    @property
    @override
    def pipe_dependencies(self) -> set[str]:
        """Return the set of pipe codes from outcomes and default_pipe_code.

        Excludes special pipe codes like 'continue'.
        """
        pipe_codes = set(self.outcomes.values())
        if self.default_outcome:
            pipe_codes.add(self.default_outcome)
        return pipe_codes - set(SpecialOutcome.value_list())
