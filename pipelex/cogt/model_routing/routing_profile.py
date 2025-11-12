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
    optional_routes: dict[str, str] = Field(default_factory=dict)
    fallback_order: list[str] | None = None  # Ordered list of backends for fallback

    def get_backend_match_for_model(self, enabled_backends: list[str], model_name: str) -> BackendMatchForModel | None:
        """Get the backend name for a given model name.

        Args:
            enabled_backends: List of enabled backends
            model_name: Name of the model to route

        Returns:
            Backend name to use for this model

        """
        possible_routes = self.routes
        for pattern, backend in self.optional_routes.items():
            if backend not in enabled_backends:
                continue
            possible_routes[pattern] = backend

        # Check exact matches first
        if (backend_name := possible_routes.get(model_name)) and (backend_name in enabled_backends):
            return BackendMatchForModel(
                model_name=model_name,
                backend_name=possible_routes[model_name],
                routing_profile_name=self.name,
                matching_method=BackendMatchingMethod.EXACT_MATCH,
                matched_pattern=None,
            )

        # Check pattern matches
        for pattern, backend in possible_routes.items():
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

        # Validate fallback_order if set
        validated_fallback_order: list[str] | None = None
        if self.fallback_order:
            validated_fallback_order = [backend for backend in self.fallback_order if backend in enabled_backends]

        # Determine primary backend for DEFAULT matching
        primary_backend: str | None = None
        if self.default and self.default in enabled_backends:
            primary_backend = self.default
        elif validated_fallback_order:
            primary_backend = validated_fallback_order[0]

        # Return default backend match if we have a primary backend
        if primary_backend:
            return BackendMatchForModel(
                model_name=model_name,
                backend_name=primary_backend,
                routing_profile_name=self.name,
                matching_method=BackendMatchingMethod.DEFAULT,
                matched_pattern=None,
                fallback_order=validated_fallback_order,
            )
        return None
