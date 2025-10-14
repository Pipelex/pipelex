from pydantic import BaseModel, Field, field_validator

from pipelex.cogt.model_backends.model_constraints import ModelConstraints
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.model_backends.prompting_target import PromptingTarget
from pipelex.cogt.usage.cost_category import CostCategory, CostsByCategoryDict
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of


class InferenceModelSpecBlueprint(ConfigModel):
    enabled: bool = True
    sdk: str
    model_type: ModelType = Field(default=ModelType.LLM, strict=False)
    model_id: str
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    costs: CostsByCategoryDict = Field(strict=False)
    max_tokens: int | None = None
    max_prompt_images: int | None = None
    prompting_target: PromptingTarget | None = Field(default=None, strict=False)
    constraints: list[ModelConstraints] = Field(default_factory=empty_list_factory_of(ModelConstraints))

    @field_validator("costs", mode="before")
    @staticmethod
    def validate_costs(value: dict[str, float]) -> CostsByCategoryDict:
        return ConfigModel.transform_dict_of_floats_str_to_enum(
            input_dict=value,
            key_enum_cls=CostCategory,
        )

    @field_validator("constraints", mode="before")
    @staticmethod
    def validate_constraints(value: list[str]) -> list[ModelConstraints]:
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
    ) -> InferenceModelSpec:
        return InferenceModelSpec(
            backend_name=backend_name,
            name=name,
            sdk=blueprint.sdk,
            model_type=blueprint.model_type,
            model_id=blueprint.model_id,
            inputs=blueprint.inputs,
            outputs=blueprint.outputs,
            costs=blueprint.costs,
            max_tokens=blueprint.max_tokens,
            max_prompt_images=blueprint.max_prompt_images,
            prompting_target=blueprint.prompting_target,
            constraints=blueprint.constraints,
        )
