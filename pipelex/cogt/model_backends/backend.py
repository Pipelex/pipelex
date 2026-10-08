from enum import StrEnum
from typing import Any

from pydantic import Field

from pipelex.cogt.model_backends.constraints import ListedConstraint, ValuedConstraint
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_spec_index import ModelSpecIndex
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.tools.typing.pydantic_utils import empty_dict_factory_of, empty_list_factory_of


class PipelexBackend(StrEnum):
    """Special Pipelex-managed inference backends."""

    INTERNAL = "internal"  # Software-only backend, runs locally without AI


class InferenceBackend(ConfigModel):
    name: str
    display_name: str | None = None
    enabled: bool = True
    endpoint: str | None = None
    api_key: str | None = None
    listed_constraints: list[ListedConstraint] = Field(default_factory=empty_list_factory_of(ListedConstraint))
    valued_constraints: dict[ValuedConstraint, Any] = Field(default_factory=empty_dict_factory_of(ValuedConstraint))
    extra_config: dict[str, Any] = Field(default_factory=dict)
    model_specs: ModelSpecIndex = Field(default_factory=ModelSpecIndex.make_empty)
    # What a keyless load (`CredentialResolution.SKIP`) left unresolved: each field it left unset, or
    # `model_specs` for the backend's own file, mapped to the names of the variables it references.
    # A field minted at boot rather than read from a variable, as Vertex AI's token is, maps to no
    # name. Empty after a load that resolved every credential, and only then may the backend be called.
    unresolved_credentials: dict[str, list[str]] = Field(default_factory=dict)

    @property
    def unresolved_credential_vars(self) -> list[str]:
        """The names of every variable this backend's credentials reference and its load left unresolved, sorted."""
        return sorted({var_name for var_names in self.unresolved_credentials.values() for var_name in var_names})

    def get_model_spec(self, *, model_type: ModelType, handle: str) -> InferenceModelSpec | None:
        """The spec this backend declares for `handle` as `model_type`, or `None`."""
        return self.model_specs.get(model_type=model_type, handle=handle)

    def get_extra_config(self, key: str) -> Any | None:
        """Get an extra config by key."""
        return self.extra_config.get(key)
