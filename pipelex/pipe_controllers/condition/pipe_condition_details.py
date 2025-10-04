from pydantic import BaseModel, Field

from pipelex.pipe_controllers.condition.pipe_condition_blueprint import OutcomeMap


class PipeConditionDetails(BaseModel):
    code: str
    test_expression: str
    outcomes: OutcomeMap = Field(default_factory=OutcomeMap)
    default_pipe_code: str | None = None
    evaluated_expression: str
    chosen_pipe_code: str
