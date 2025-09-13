from typing import Dict

from pydantic import Field

from pipelex.tools.config.config_model import ConfigModel


class ModelCatalogConfig(ConfigModel):
    """Configuration for model routing to backends."""

    description: str
    default: str  # Default backend name
    routes: Dict[str, str] = Field(default_factory=dict)  # Pattern -> Backend mapping

    def get_backend_for_model(self, model_name: str) -> str:
        """Get the backend name for a given model name.

        Args:
            model_name: Name of the model to route

        Returns:
            Backend name to use for this model
        """
        # Check exact matches first
        if model_name in self.routes:
            return self.routes[model_name]

        # Check pattern matches
        for pattern, backend in self.routes.items():
            if self._matches_pattern(model_name, pattern):
                return backend

        # Return default backend
        return self.default

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
