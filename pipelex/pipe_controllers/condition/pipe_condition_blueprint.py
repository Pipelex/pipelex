from typing import Literal

from pydantic import Field, field_validator, model_validator
from typing_extensions import override

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.tools.typing.validation_utils import has_exactly_one_among_attributes_from_list
from pipelex.types import Self

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
            msg = f"PipeConditionBlueprint must have at least one mapping in outcomes, got: {outcomes}"
            raise ValueError(msg)
        return outcomes

    @model_validator(mode="after")
    def validate_expression_and_expression_template(self) -> Self:
        if not has_exactly_one_among_attributes_from_list(self, attributes_list=["expression_template", "expression"]):
            msg = "PipeCondition should have exactly one of 'expression_template' or 'expression'"
            raise ValueError(msg)
        return self

    @override
    def validate_inputs(self):
        pass

    @override
    def validate_output(self):
        pass
