from typing import List, Optional

from pydantic import BaseModel, Field

from pipelex.cogt.inference.inference_backend import InferenceBackend
from pipelex.cogt.inference.inference_backend_service import InferenceService
from pipelex.cogt.inference.inference_model_spec import InferenceModelSpec


class InferenceBackendBlueprint(BaseModel):
    enabled: bool = True
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    services: List[InferenceService] = Field(default_factory=list)


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
            services=inference_backend_blueprint.services,
            model_specs=model_specs,
        )
