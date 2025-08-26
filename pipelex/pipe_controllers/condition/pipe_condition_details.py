from typing import List, Optional

from pydantic import BaseModel


class PipeConditionPipeMap(BaseModel):
    expression_result: str
    pipe_code: str


class PipeConditionDetails(BaseModel):
    code: str
    test_expression: str
    pipe_map: List[PipeConditionPipeMap]
    default_pipe_code: Optional[str] = None
    evaluated_expression: str
    chosen_pipe_code: str
