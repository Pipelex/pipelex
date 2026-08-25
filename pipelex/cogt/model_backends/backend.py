from enum import StrEnum
from typing import Any

from pydantic import Field

from pipelex.cogt.model_backends.constraints import ListedConstraint, ValuedConstraint
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.tools.typing.pydantic_utils import empty_dict_factory_of, empty_list_factory_of

# The remote-config section the legacy gateway backend's specs come from. It is spelled here as a
# *compatibility default* rather than only in the shipped `backends.toml`, and the distinction
# matters: `backends.toml` is the user's own file on disk, written before this field existed and
# never rewritten by an upgrade, so a declaration that does not name a section has to keep meaning
# what it always meant. Every new managed backend states its section explicitly.
LEGACY_GATEWAY_MODEL_SPECS_SECTION = "backend_model_specs"

# The section the manifold dialect's catalog is published under, beside the legacy one in the same
# artifact. Named here so the kit config, the fetcher's dummy and the tests cannot drift apart on a
# string literal.
MANIFOLD_MODEL_SPECS_SECTION = "manifold_model_specs"


class PipelexBackend(StrEnum):
    """Special Pipelex-managed inference backends."""

    GATEWAY = "pipelex_gateway"
    MANIFOLD = "pipelex_manifold"
    INTERNAL = "internal"  # Software-only backend, runs locally without AI

    @property
    def display_name(self) -> str:
        match self:
            case PipelexBackend.GATEWAY:
                return "Pipelex Gateway"
            case PipelexBackend.MANIFOLD:
                return "Pipelex Manifold"
            case PipelexBackend.INTERNAL:
                return "Internal (software-only)"


# The Pipelex-managed gateway backends the kit ships, in a stable order so a message built from them
# reads the same every time.
#
# This is a *second*, narrower way of naming a managed gateway than `resolve_model_specs_section`, and
# it exists for the callers that hold only a backend name and no configuration — an inference worker
# asserting a provider behaviour that follows from running behind our gateway codebase, for instance.
# Wherever the configuration is in hand, the declared section is the authority.
MANAGED_GATEWAY_BACKEND_NAMES: tuple[str, ...] = (PipelexBackend.GATEWAY, PipelexBackend.MANIFOLD)


def resolve_model_specs_section(*, backend_name: str, declared_section: str | None) -> str | None:
    """The remote-config section this backend's model specs come from, or `None` when it has none.

    **Declaring a section is what makes a backend a managed gateway backend**: its model specs
    arrive from the Pipelex service's published artifact rather than from a local per-backend TOML.
    A backend with no section resolves to `None` and loads its specs from its own file, which is
    every BYOK backend and the internal one.

    The one name that resolves to a section it did not declare is `pipelex_gateway`, and only
    because its declarations predate the field — see `LEGACY_GATEWAY_MODEL_SPECS_SECTION`. An
    explicit declaration always wins, including on that name.
    """
    if declared_section is not None:
        return declared_section
    if backend_name == PipelexBackend.GATEWAY:
        return LEGACY_GATEWAY_MODEL_SPECS_SECTION
    return None


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
