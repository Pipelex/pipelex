from typing import Any

from pydantic import Field, field_validator

from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.constraints import ListedConstraint, ValuedConstraint
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.openai.vertexai_factory import VertexAIFactory
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.tools.typing.pydantic_utils import empty_dict_factory_of, empty_list_factory_of


class InferenceBackendBlueprint(ConfigModel):
    enabled: bool = True
    endpoint: str | None = None
    api_key: str | None = None
    listed_constraints: list[ListedConstraint] = Field(default_factory=empty_list_factory_of(ListedConstraint))
    valued_constraints: dict[ValuedConstraint, Any] = Field(default_factory=empty_dict_factory_of(ValuedConstraint))
    extra_config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("listed_constraints", mode="before")
    @classmethod
    def validate_listed_constraints(cls, value: list[str]) -> list[ListedConstraint]:
        return ConfigModel.transform_list_of_str_to_enum(
            input_list=value,
            enum_cls=ListedConstraint,
        )

    @field_validator("valued_constraints", mode="before")
    @classmethod
    def validate_valued_constraints(cls, value: dict[str, Any]) -> dict[ValuedConstraint, Any]:
        return ConfigModel.transform_dict_keys_str_to_enum(
            input_dict=value,
            key_enum_cls=ValuedConstraint,
        )


class InferenceBackendFactory:
    @classmethod
    def make_inference_backend(
        cls,
        name: str,
        blueprint: InferenceBackendBlueprint,
        extra_config: dict[str, Any],
        model_specs: dict[str, InferenceModelSpec],
    ) -> InferenceBackend:
        endpoint = blueprint.endpoint
        api_key = blueprint.api_key
        # Deal with special authentication for some backends
        match name:
            case "vertexai":
                endpoint, api_key = VertexAIFactory.make_endpoint_and_api_key(extra_config=extra_config)
            case _:
                pass
        return InferenceBackend(
            name=name,
            enabled=blueprint.enabled,
            endpoint=endpoint,
            api_key=api_key,
            listed_constraints=blueprint.listed_constraints,
            valued_constraints=blueprint.valued_constraints,
            extra_config=extra_config,
            model_specs=model_specs,
        )
