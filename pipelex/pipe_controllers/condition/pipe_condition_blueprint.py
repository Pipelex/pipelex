from typing import Literal

from pydantic import Field, field_validator
from typing_extensions import override

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.pipe_controllers.condition.exceptions import PipeConditionBlueprintValueError
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

    @field_validator("outcomes", mode="after")
    @classmethod
    def validate_outcome_map(cls, outcomes: OutcomeMap) -> OutcomeMap:
        if not outcomes:
            msg = "PipeConditionBlueprint must have at least one mapping in outcomes"
            raise PipeConditionBlueprintValueError(msg)
        return outcomes

    @override
    def _validate_inputs(self):
        pass

    @override
    def _validate_output(self):
        pass
