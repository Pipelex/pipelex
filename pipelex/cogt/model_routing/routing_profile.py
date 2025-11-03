from pydantic import Field

from pipelex.cogt.model_routing.routing_models import BackendMatchForModel, BackendMatchingMethod
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.tools.misc.string_utils import matches_wildcard_pattern


class RoutingProfile(ConfigModel):
    """Configuration for model routing to backends."""

    name: str
    description: str | None = None
    default: str | None = None
    routes: dict[str, str] = Field(default_factory=dict)  # Pattern -> Backend mapping

    def get_backend_match_for_model(self, enabled_backends: list[str], model_name: str) -> BackendMatchForModel | None:
        """Get the backend name for a given model name.

        Args:
            enabled_backends: List of enabled backends
            model_name: Name of the model to route

        Returns:
            Backend name to use for this model

        """
        # Check exact matches first
        if (backend_name := self.routes.get(model_name)) and (backend_name in enabled_backends):
            return BackendMatchForModel(
                model_name=model_name,
                backend_name=self.routes[model_name],
                routing_profile_name=self.name,
                matching_method=BackendMatchingMethod.EXACT_MATCH,
                matched_pattern=None,
            )

        # Check pattern matches
        for pattern, backend in self.routes.items():
            if backend not in enabled_backends:
                continue
            if matches_wildcard_pattern(model_name, pattern):
                return BackendMatchForModel(
                    model_name=model_name,
                    backend_name=backend,
                    routing_profile_name=self.name,
                    matching_method=BackendMatchingMethod.PATTERN_MATCH,
                    matched_pattern=pattern,
                )

        # Return default backend
        if self.default and self.default in enabled_backends:
            return BackendMatchForModel(
                model_name=model_name,
                backend_name=self.default,
                routing_profile_name=self.name,
                matching_method=BackendMatchingMethod.DEFAULT,
                matched_pattern=None,
            )
        return None
