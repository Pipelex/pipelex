from typing import Any, Dict, Optional

from pydantic import Field

from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.hub import get_plugin_manager
from pipelex.tools.config.config_model import ConfigModel


class InferenceBackendBlueprint(ConfigModel):
    enabled: bool = True
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    extra_config: Dict[str, Any] = Field(default_factory=dict)


class InferenceBackendFactory:
    @classmethod
    def make_inference_backend(
        cls,
        name: str,
        blueprint: InferenceBackendBlueprint,
        extra_config: Dict[str, Any],
        model_specs: Dict[str, InferenceModelSpec],
    ) -> InferenceBackend:
        endpoint = blueprint.endpoint
        api_key = blueprint.api_key
        # api_version = blueprint.api_version
        # Deal with special authentication for some backends
        match name:
            case "vertexai":
                from pipelex.plugins.openai.vertexai_factory import VertexAIFactory

                endpoint, api_key = VertexAIFactory.make_endpoint_and_api_key(extra_config=extra_config)
            case _:
                pass
        return InferenceBackend(
            name=name,
            endpoint=endpoint,
            api_key=api_key,
            extra_config=extra_config,
            model_specs=model_specs,
        )
