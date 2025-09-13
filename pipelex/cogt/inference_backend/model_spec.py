from typing import List, Optional

from pydantic import BaseModel, Field

from pipelex.cogt.llm.token_category import TokenCostsByCategoryDict


class InferenceModelSpec(BaseModel):
    sdk: str
    model_id: str
    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)
    costs: TokenCostsByCategoryDict
    max_tokens: Optional[int]
    max_prompt_images: Optional[int]
