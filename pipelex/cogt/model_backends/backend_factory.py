from typing import List, Optional

from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.tools.config.config_model import ConfigModel


class InferenceBackendBlueprint(ConfigModel):
    enabled: bool = True
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
