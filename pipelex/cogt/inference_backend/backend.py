from typing import List, Optional

from pydantic import Field

from pipelex.cogt.inference_backend.model_spec import InferenceModelSpec
from pipelex.config import ConfigModel


class InferenceBackend(ConfigModel):
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    model_specs: List[InferenceModelSpec] = Field(default_factory=list)
