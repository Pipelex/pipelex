from typing import Any, Dict, List, Optional

from pydantic import Field

from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.tools.config.config_model import ConfigModel


class InferenceBackend(ConfigModel):
    name: str
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    extra_config: Dict[str, Any] = Field(default_factory=dict)
    model_specs: Dict[str, InferenceModelSpec] = Field(default_factory=dict)

    def list_model_names(self) -> List[str]:
        """List the names of all models in the backend."""
        return list(self.model_specs.keys())

    def get_model_spec(self, model_name: str) -> Optional[InferenceModelSpec]:
        """Get a model spec by name."""
        model_spec = self.model_specs.get(model_name)
        return model_spec

    def get_extra_config(self, key: str) -> Optional[Any]:
        """Get an extra config by key."""
        return self.extra_config.get(key)
