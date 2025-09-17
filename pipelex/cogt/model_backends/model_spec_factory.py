from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from pipelex.cogt.exceptions import InferenceModelSpecError
from pipelex.cogt.model_backends.model_constraints import ModelConstraints
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.prompting_target import PromptingTarget
from pipelex.cogt.usage.cost_category import CostCategory, CostsByCategoryDict
from pipelex.tools.config.config_model import ConfigModel


class InferenceModelSpecBlueprint(ConfigModel):
    enabled: bool = True
    sdk: Optional[str] = None
    model_id: str
    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)
    costs: CostsByCategoryDict = Field(strict=False)
    max_tokens: Optional[int] = None
    max_prompt_images: Optional[int] = None
    prompting_target: Optional[PromptingTarget] = Field(default=None, strict=False)
    constraints: List[ModelConstraints] = Field(default_factory=list)

    @field_validator("costs", mode="before")
    def validate_costs(cls, value: Dict[str, float]) -> CostsByCategoryDict:
        return ConfigModel.transform_dict_of_floats_str_to_enum(
            input_dict=value,
            key_enum_cls=CostCategory,
        )

    @field_validator("constraints", mode="before")
    def validate_constraints(cls, value: List[str]) -> List[ModelConstraints]:
        return ConfigModel.transform_list_of_str_to_enum(
            input_list=value,
            enum_cls=ModelConstraints,
        )


class InferenceModelSpecFactory(BaseModel):
    @classmethod
    def make_inference_model_spec(
        cls,
        backend_name: str,
        name: str,
        blueprint: InferenceModelSpecBlueprint,
        default_prompting_target: Optional[PromptingTarget],
        fallback_sdk: Optional[str],
    ) -> InferenceModelSpec:
        sdk = blueprint.sdk or fallback_sdk
        if not sdk:
            raise InferenceModelSpecError("No sdk choice provided")
        prompting_target = blueprint.prompting_target or default_prompting_target
        return InferenceModelSpec(
            backend_name=backend_name,
            name=name,
            sdk=sdk,
            model_id=blueprint.model_id,
            inputs=blueprint.inputs,
            outputs=blueprint.outputs,
            costs=blueprint.costs,
            max_tokens=blueprint.max_tokens,
            max_prompt_images=blueprint.max_prompt_images,
            prompting_target=prompting_target,
            constraints=blueprint.constraints,
        )
