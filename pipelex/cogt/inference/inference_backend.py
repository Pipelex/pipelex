from typing import List, Optional

from pydantic import BaseModel, Field

from pipelex.cogt.inference.inference_backend_service import InferenceService
from pipelex.cogt.inference.inference_model_spec import InferenceModelSpec
from pipelex.types import StrEnum


class InferenceBackend(BaseModel):
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    services: List[InferenceService] = Field(default_factory=list)
    model_specs: List[InferenceModelSpec] = Field(default_factory=list)
