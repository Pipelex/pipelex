from typing import Dict, Optional

from pydantic import Field, RootModel, ValidationError

from pipelex import log
from pipelex.cogt.exceptions import ModelCatalogLibraryError, RoutingProfileLibraryError
from pipelex.cogt.model_routing.routing_profile import RoutingProfile
from pipelex.cogt.model_routing.routing_profile_factory import (
    ModelCatalogBlueprint,
    RoutingProfileFactory,
)
from pipelex.config import get_config
from pipelex.tools.misc.toml_utils import TOMLValidationError, load_toml_from_path

RoutingProfileLibraryRoot = Dict[str, RoutingProfile]


class RoutingProfileLibrary(RootModel[RoutingProfileLibraryRoot]):
    """Library for managing model catalog configurations."""

    root: RoutingProfileLibraryRoot = Field(default_factory=dict)
    _active_config: Optional[str] = None

    @classmethod
    def make_empty(cls):
        return cls(root={})

    def reset(self) -> None:
        self.root = {}

    def load(self) -> None:
        """Load the model catalog configuration from TOML file."""
        routing_profile_library_path = get_config().cogt.inference_config.routing_profile_library_path

        try:
            catalog_dict = load_toml_from_path(
                path=routing_profile_library_path,
                is_env_var_substitution_enabled=True,
            )
        except (FileNotFoundError, TOMLValidationError) as exc:
            raise ModelCatalogLibraryError(f"Failed to load routing profile library from file '{routing_profile_library_path}': {exc}") from exc

        try:
            catalog_blueprint = ModelCatalogBlueprint.model_validate(catalog_dict)
        except ValidationError as exc:
            raise ModelCatalogLibraryError(f"Invalid routing profile library configuration in '{routing_profile_library_path}': {exc}") from exc

        # Validate that the active config exists
        if catalog_blueprint.active not in catalog_blueprint.configs:
            raise ModelCatalogLibraryError(
                f"Active configuration '{catalog_blueprint.active}' not found in library. "
                f"Available configurations: {list(catalog_blueprint.configs.keys())}"
            )

        # Load all configurations
        self.root = {}
        for config_name, config_blueprint in catalog_blueprint.configs.items():
            self.root[config_name] = RoutingProfileFactory.make_routing_profile(blueprint=config_blueprint)
        self._active_config = catalog_blueprint.active

        log.debug(f"Loaded model catalog with active configuration: '{self._active_config}'")
        log.debug(f"Available configurations: {list(self.root.keys())}")

    def get_backend_for_model(self, model_name: str) -> str:
        """Get the backend name for a given model.

        Args:
            model_name: Name of the model to route

        Returns:
            Backend name to use for this model

        Raises:
            ModelCatalogError: If no active configuration is set or config not found
        """
        if not self._active_config:
            raise RoutingProfileLibraryError("No active model catalog configuration loaded")

        if self._active_config not in self.root:
            raise RoutingProfileLibraryError(f"Active configuration '{self._active_config}' not found in loaded catalog")

        active_config = self.root[self._active_config]
        backend = active_config.get_backend_for_model(model_name)

        log.debug(f"Routing model '{model_name}' to backend '{backend}' using config '{self._active_config}'")
        return backend

    def get_active_routing_profile_name(self) -> Optional[str]:
        """Get the name of the currently active configuration."""
        return self._active_config

    def list_routing_profile_names(self) -> list[str]:
        """Get a list of all available routing profile names."""
        return list(self.root.keys())

    def get_required_routing_profile(self, routing_profile_name: str) -> RoutingProfile:
        routing_profile = self.root.get(routing_profile_name)
        if not routing_profile:
            raise RoutingProfileLibraryError(f"Routing profile '{routing_profile_name}' not found in loaded routing profile library")
        return routing_profile

    def get_required_active_routing_profile(self) -> RoutingProfile:
        """Get the required active routing profile."""
        if not self._active_config:
            raise RoutingProfileLibraryError("No active routing profile loaded")

        active_config_name: str = self._active_config

        active_routing_profile = self.get_required_routing_profile(routing_profile_name=active_config_name)
        return active_routing_profile
