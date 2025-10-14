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

    def get_backend_match_for_model(self, model_name: str) -> BackendMatchForModel | None:
        """Get the backend name for a given model name.

        Args:
            model_name: Name of the model to route

        Returns:
            Backend name to use for this model

        """
        # Check exact matches first
        if model_name in self.routes:
            return BackendMatchForModel(
                model_name=model_name,
                backend_name=self.routes[model_name],
                routing_profile_name=self.name,
                matching_method=BackendMatchingMethod.EXACT_MATCH,
                matched_pattern=None,
            )

        # Check pattern matches
        for pattern, backend in self.routes.items():
            if matches_wildcard_pattern(model_name, pattern):
                return BackendMatchForModel(
                    model_name=model_name,
                    backend_name=backend,
                    routing_profile_name=self.name,
                    matching_method=BackendMatchingMethod.PATTERN_MATCH,
                    matched_pattern=pattern,
                )

        # Return default backend
        if self.default:
            return BackendMatchForModel(
                model_name=model_name,
                backend_name=self.default,
                routing_profile_name=self.name,
                matching_method=BackendMatchingMethod.DEFAULT,
                matched_pattern=None,
            )
        return None
