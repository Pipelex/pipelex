from typing import Dict, Optional

from pydantic import Field

from pipelex.cogt.model_routing.routing_models import BackendMatchForModel, BackendMatchingMethod
from pipelex.tools.config.config_model import ConfigModel


class RoutingProfile(ConfigModel):
    """Configuration for model routing to backends."""

    name: str
    description: Optional[str] = None
    default: Optional[str] = None
    routes: Dict[str, str] = Field(default_factory=dict)  # Pattern -> Backend mapping

    def get_backend_match_for_model(self, model_name: str) -> Optional[BackendMatchForModel]:
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
            if self._matches_pattern(model_name, pattern):
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
        else:
            return None

    def _matches_pattern(self, model_name: str, pattern: str) -> bool:
        """Check if a model name matches a pattern.

        Supports wildcards (*) at the beginning, end, or both.

        Args:
            model_name: The model name to check
            pattern: The pattern to match against

        Returns:
            True if the model name matches the pattern
        """
        if pattern == "*":
            return True

        if pattern.startswith("*") and pattern.endswith("*"):
            # Pattern like "*sonnet*"
            middle = pattern[1:-1]
            return middle in model_name
        elif pattern.startswith("*"):
            # Pattern like "*sonnet"
            suffix = pattern[1:]
            return model_name.endswith(suffix)
        elif pattern.endswith("*"):
            # Pattern like "claude-*"
            prefix = pattern[:-1]
            return model_name.startswith(prefix)
        else:
            # Exact match
            return model_name == pattern
