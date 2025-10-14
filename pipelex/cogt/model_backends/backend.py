from typing import Any

from pydantic import Field

from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.system.configuration.config_model import ConfigModel


class InferenceBackend(ConfigModel):
    name: str
    endpoint: str | None = None
    api_key: str | None = None
    extra_config: dict[str, Any] = Field(default_factory=dict)
    model_specs: dict[str, InferenceModelSpec] = Field(default_factory=dict)

    def list_model_names(self) -> list[str]:
        """List the names of all models in the backend."""
        return list(self.model_specs.keys())

    def get_model_spec(self, model_name: str) -> InferenceModelSpec | None:
        """Get a model spec by name."""
        return self.model_specs.get(model_name)

    def get_extra_config(self, key: str) -> Any | None:
        """Get an extra config by key."""
        return self.extra_config.get(key)
