from pydantic import BaseModel

PipeConditionPipeMap = dict[str, str]


class PipeConditionDetails(BaseModel):
    code: str
    test_expression: str
    pipe_map: dict[str, str]
    default_pipe_code: str | None = None
    evaluated_expression: str
    chosen_pipe_code: str
