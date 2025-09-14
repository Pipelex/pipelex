from typing import Dict, Optional

from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.hub import get_plugin_manager, get_secrets_provider
from pipelex.tools.config.config_model import ConfigModel


class InferenceBackendBlueprint(ConfigModel):
    enabled: bool = True
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    api_version: Optional[str] = None


class InferenceBackendFactory:
    @classmethod
    def make_inference_backend(
        cls,
        name: str,
        blueprint: InferenceBackendBlueprint,
        model_specs: Dict[str, InferenceModelSpec],
    ) -> InferenceBackend:
        endpoint = blueprint.endpoint
        api_key = blueprint.api_key
        api_version = blueprint.api_version
        # Deal with special authentication for some backends
        match name:
            case "vertexai":
                vertexai_config = get_plugin_manager().plugin_configs.vertexai_config
                endpoint, api_key = vertexai_config.configure(secrets_provider=get_secrets_provider())
            case _:
                pass
        return InferenceBackend(
            name=name,
            endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
            model_specs=model_specs,
        )
