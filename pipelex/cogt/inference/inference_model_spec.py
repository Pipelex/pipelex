from typing import List, Optional

from pydantic import BaseModel, Field

from pipelex.cogt.llm.token_category import TokenCostsByCategoryDict


class InferenceModelSpec(BaseModel):
    sdk: str
    model_id: str
    features: List[str] = Field(default_factory=list)
    cost_per_million_tokens_usd: TokenCostsByCategoryDict
    max_tokens: Optional[int]
    max_prompt_images: Optional[int]
