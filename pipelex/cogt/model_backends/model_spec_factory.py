from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from pipelex.cogt.exceptions import InferenceModelSpecError
from pipelex.cogt.model_backends.cost_category import CostCategory
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.tools.config.config_model import ConfigModel


class InferenceModelSpecBlueprint(ConfigModel):
    enabled: bool = True
    sdk: Optional[str] = None
    model_id: str
    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)
    costs: Dict[CostCategory, float] = Field(strict=False)
    max_tokens: Optional[int] = None
    max_prompt_images: Optional[int] = None

    @field_validator("costs", mode="before")
    def validate_costs(cls, value: Dict[str, float]) -> Dict[CostCategory, float]:
        return ConfigModel.transform_dict_of_floats_str_to_enum(
            input_dict=value,
            key_enum_cls=CostCategory,
        )


class InferenceModelSpecFactory(BaseModel):
    @classmethod
    def make_inference_model_spec(
        cls,
        name: str,
        blueprint: InferenceModelSpecBlueprint,
        default_sdk: Optional[str],
    ) -> InferenceModelSpec:
        sdk = blueprint.sdk or default_sdk
        if not sdk:
            raise InferenceModelSpecError("No sdk choice provided")
        return InferenceModelSpec(
            name=name,
            sdk=sdk,
            model_id=blueprint.model_id,
            inputs=blueprint.inputs,
            outputs=blueprint.outputs,
            costs=blueprint.costs,
            max_tokens=blueprint.max_tokens,
            max_prompt_images=blueprint.max_prompt_images,
        )
