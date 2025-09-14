from typing import List, Optional

from pydantic import Field

from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.tools.config.config_model import ConfigModel


class InferenceBackend(ConfigModel):
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    model_specs: List[InferenceModelSpec] = Field(default_factory=list)
