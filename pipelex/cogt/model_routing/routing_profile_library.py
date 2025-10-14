from pydantic import Field, RootModel, ValidationError

from pipelex import log
from pipelex.cogt.exceptions import RoutingProfileLibraryError, RoutingProfileLibraryNotFoundError, RoutingProfileValidationError
from pipelex.cogt.model_routing.routing_models import BackendMatchForModel
from pipelex.cogt.model_routing.routing_profile import RoutingProfile
from pipelex.cogt.model_routing.routing_profile_factory import (
    RoutingProfileFactory,
    RoutingProfileLibraryBlueprint,
)
from pipelex.config import get_config
from pipelex.tools.misc.toml_utils import load_toml_from_path
from pipelex.types import Self

RoutingProfileLibraryRoot = dict[str, RoutingProfile]


class RoutingProfileLibrary(RootModel[RoutingProfileLibraryRoot]):
    """Library for managing routing profile configurations."""

    root: RoutingProfileLibraryRoot = Field(default_factory=dict)
    _active_config: str | None = None

    @property
    def active_profile(self) -> RoutingProfile:
        if not self._active_config:
            msg = "No active routing profile loaded"
            raise RoutingProfileLibraryError(msg)
        if self._active_config not in self.root:
            msg = f"Active routing profile '{self._active_config}' not found in loaded routing profile library"
            raise RoutingProfileLibraryError(msg)
        return self.root[self._active_config]

    @classmethod
    def make_empty(cls) -> Self:
        return cls(root={})

    def reset(self) -> None:
        self.root = {}

    def load(self) -> None:
        """Load the routing profile library configuration from TOML file."""
        routing_profile_library_path = get_config().cogt.inference_config.routing_profile_library_path

        try:
            catalog_dict = load_toml_from_path(path=routing_profile_library_path)
        except FileNotFoundError as not_found_exc:
            msg = f"Could not find routing profile library at '{routing_profile_library_path}': {not_found_exc}"
            raise RoutingProfileLibraryNotFoundError(msg) from not_found_exc

        try:
            catalog_blueprint = RoutingProfileLibraryBlueprint.model_validate(catalog_dict)
        except ValidationError as exc:
            msg = f"Invalid routing profile library configuration in '{routing_profile_library_path}': {exc}"
            raise RoutingProfileValidationError(msg) from exc

        # Validate that the active config exists
        if catalog_blueprint.active not in catalog_blueprint.profiles:
            msg = f"Active profile '{catalog_blueprint.active}' not found in library. Available profiles: {list(catalog_blueprint.profiles.keys())}"
            raise RoutingProfileLibraryError(msg)

        # Load all profiles
        self.root = {}
        for config_name, config_blueprint in catalog_blueprint.profiles.items():
            self.root[config_name] = RoutingProfileFactory.make_routing_profile(
                name=config_name,
                blueprint=config_blueprint,
            )
        self._active_config = catalog_blueprint.active

        log.debug(f"Loaded routing profile library with active profile: '{self._active_config}'")
        log.debug(f"Available profiles: {list(self.root.keys())}")

    def get_backend_match_for_model_from_active_routing_profile(self, model_name: str) -> BackendMatchForModel | None:
        """Get the backend name for a given model.

        Args:
            model_name: Name of the model to route

        Returns:
            Backend name to use for this model

        Raises:
            RoutingProfileLibraryError: If no active profile is set or config not found

        """
        profile = self.active_profile
        return profile.get_backend_match_for_model(model_name)

    def list_routing_profile_names(self) -> list[str]:
        """Get a list of all available routing profile names."""
        return list(self.root.keys())

    def get_required_routing_profile(self, routing_profile_name: str) -> RoutingProfile:
        routing_profile = self.root.get(routing_profile_name)
        if not routing_profile:
            msg = f"Routing profile '{routing_profile_name}' not found in loaded routing profile library"
            raise RoutingProfileLibraryError(msg)
        return routing_profile
