from typing import Dict, List, Optional, cast

from pydantic import Field, field_validator

from pipelex.cogt.inference_backend.cost_category import CostCategory
from pipelex.config import ConfigModel


class InferenceModelSpec(ConfigModel):
    sdk: str
    model_id: str
    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)
    costs: Dict[CostCategory, float] = Field(strict=False)
    max_tokens: Optional[int]
    max_prompt_images: Optional[int]
