from typing import List, Optional

from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.tools.config.config_model import ConfigModel


class InferenceBackendBlueprint(ConfigModel):
    enabled: bool = True
    endpoint: Optional[str] = None
    api_key: Optional[str] = None


class InferenceBackendFactory:
    @classmethod
    def make_inference_backend(
        cls,
        inference_backend_blueprint: InferenceBackendBlueprint,
        model_specs: List[InferenceModelSpec],
    ) -> InferenceBackend:
        return InferenceBackend(
            endpoint=inference_backend_blueprint.endpoint,
            api_key=inference_backend_blueprint.api_key,
            model_specs=model_specs,
        )
