from typing import Any

from pydantic import BaseModel, Field, field_validator

from pipelex.cogt.img_gen.img_gen_model_rules import ImgGenArgTopic, ImgGenModelRules
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.cogt.model_backends.constraints import ListedConstraint, ValuedConstraint
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.model_backends.prompting_target import PromptingTarget
from pipelex.cogt.usage.cost_category import CostCategory, CostsByCategoryDict
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.tools.typing.pydantic_utils import empty_dict_factory_of, empty_list_factory_of

BackendModelSpecs = dict[str, Any]


class InferenceModelSpecBlueprint(ConfigModel):
    enabled: bool = True
    sdk: str
    variant: str | None = None
    model_type: ModelType = Field(default=ModelType.LLM, strict=False)
    model_id: str | None = None
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    costs: CostsByCategoryDict | None = Field(default=None, strict=False)
    structure_method: StructureMethod | None = Field(default=None, strict=False)
    max_tokens: int | None = None
    max_prompt_images: int | None = None
    prompting_target: PromptingTarget | None = Field(default=None, strict=False)
    listed_constraints: list[ListedConstraint] = Field(default_factory=empty_list_factory_of(ListedConstraint))
    valued_constraints: dict[ValuedConstraint, Any] = Field(default_factory=empty_dict_factory_of(ValuedConstraint))
    rules: ImgGenModelRules | None = None

    @field_validator("rules", mode="before")
    @staticmethod
    def validate_rules(value: dict[str, str] | None) -> ImgGenModelRules | None:
        if value is None:
            return None
        return ConfigModel.transform_dict_keys_str_to_enum(
            input_dict=value,
            key_enum_cls=ImgGenArgTopic,
        )

    @field_validator("costs", mode="before")
    @staticmethod
    def validate_costs(value: dict[str, float]) -> CostsByCategoryDict:
        return ConfigModel.transform_dict_of_floats_str_to_enum(
            input_dict=value,
            key_enum_cls=CostCategory,
        )

    @field_validator("listed_constraints", mode="before")
    @staticmethod
    def validate_listed_constraints(value: list[str]) -> list[ListedConstraint]:
        return ConfigModel.transform_list_of_str_to_enum(
            input_list=value,
            enum_cls=ListedConstraint,
        )

    @field_validator("valued_constraints", mode="before")
    @staticmethod
    def validate_valued_constraints(value: dict[str, Any]) -> dict[ValuedConstraint, Any]:
        return ConfigModel.transform_dict_keys_str_to_enum(
            input_dict=value,
            key_enum_cls=ValuedConstraint,
        )


class InferenceModelSpecFactory(BaseModel):
    @classmethod
    def make_inference_model_spec(
        cls,
        backend_name: str,
        name: str,
        blueprint: InferenceModelSpecBlueprint,
        backend_listed_constraints: list[ListedConstraint],
        backend_valued_constraints: dict[ValuedConstraint, Any],
        extra_headers: dict[str, str] | None = None,
    ) -> InferenceModelSpec:
        # Merge constraints: backend as base, model-level adds/overrides
        # Listed constraints: union of backend + model (model can add, not remove)
        merged_listed_constraints = list(set(backend_listed_constraints + blueprint.listed_constraints))
        # Valued constraints: backend as base, model overrides
        merged_valued_constraints = {**backend_valued_constraints, **blueprint.valued_constraints}

        return InferenceModelSpec(
            backend_name=backend_name,
            name=name,
            sdk=blueprint.sdk,
            variant=blueprint.variant,
            model_type=blueprint.model_type,
            model_id=blueprint.model_id or name,
            inputs=blueprint.inputs,
            outputs=blueprint.outputs,
            costs=blueprint.costs or {},
            structure_method=blueprint.structure_method,
            max_tokens=blueprint.max_tokens,
            max_prompt_images=blueprint.max_prompt_images,
            prompting_target=blueprint.prompting_target,
            listed_constraints=merged_listed_constraints,
            valued_constraints=merged_valued_constraints,
            extra_headers=extra_headers,
            rules=blueprint.rules,
        )
