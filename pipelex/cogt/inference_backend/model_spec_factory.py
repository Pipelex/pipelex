from typing import List, Optional

from pydantic import BaseModel, Field

from pipelex.cogt.exceptions import InferenceModelSpecError
from pipelex.cogt.inference_backend.model_spec import InferenceModelSpec
from pipelex.cogt.llm.token_category import TokenCostsByCategoryDict


class InferenceModelSpecBlueprint(BaseModel):
    enabled: bool = True
    sdk: Optional[str] = None
    model_id: str
    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)
    costs: TokenCostsByCategoryDict
    max_tokens: Optional[int] = None
    max_prompt_images: Optional[int] = None


class InferenceModelSpecFactory(BaseModel):
    @classmethod
    def make_inference_model_spec(
        cls,
        blueprint: InferenceModelSpecBlueprint,
        default_sdk: Optional[str],
    ) -> InferenceModelSpec:
        sdk = blueprint.sdk or default_sdk
        if not sdk:
            raise InferenceModelSpecError("No sdk choice provided")
        return InferenceModelSpec(
            sdk=sdk,
            model_id=blueprint.model_id,
            inputs=blueprint.inputs,
            outputs=blueprint.outputs,
            costs=blueprint.costs,
            max_tokens=blueprint.max_tokens,
            max_prompt_images=blueprint.max_prompt_images,
        )
