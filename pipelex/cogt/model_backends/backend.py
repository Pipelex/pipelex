from typing import Any

from pydantic import Field

from pipelex.cogt.model_backends.constraints import ListedConstraint, ValuedConstraint
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.tools.typing.pydantic_utils import empty_dict_factory_of, empty_list_factory_of
from pipelex.types import StrEnum


class PipelexBackend(StrEnum):
    """Special Pipelex-managed inference backends."""

    GATEWAY = "pipelex_gateway"
    LEGACY_INFERENCE = "pipelex_inference"  # Legacy, deprecated

    @property
    def display_name(self) -> str:
        match self:
            case PipelexBackend.GATEWAY:
                return "Pipelex Gateway"
            case PipelexBackend.LEGACY_INFERENCE:
                return "Pipelex Inference (deprecated)"

    @classmethod
    def is_gateway_backend(cls, backend_name: str) -> bool:
        try:
            the_backend = cls(backend_name)
        except ValueError:
            return False
        match the_backend:
            case PipelexBackend.GATEWAY:
                return True
            case PipelexBackend.LEGACY_INFERENCE:
                return False


class InferenceBackend(ConfigModel):
    name: str
    display_name: str | None = None
    enabled: bool = True
    endpoint: str | None = None
    api_key: str | None = None
    listed_constraints: list[ListedConstraint] = Field(default_factory=empty_list_factory_of(ListedConstraint))
    valued_constraints: dict[ValuedConstraint, Any] = Field(default_factory=empty_dict_factory_of(ValuedConstraint))
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
