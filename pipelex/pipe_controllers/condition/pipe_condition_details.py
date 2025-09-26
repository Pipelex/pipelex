from pydantic import BaseModel


class PipeConditionPipeMap(BaseModel):
    expression_result: str
    pipe_code: str


class PipeConditionDetails(BaseModel):
    code: str
    test_expression: str
    pipe_map: list[PipeConditionPipeMap]
    default_pipe_code: str | None = None
    evaluated_expression: str
    chosen_pipe_code: str
