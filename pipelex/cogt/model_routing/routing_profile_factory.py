from typing import Dict

from pydantic import Field

from pipelex.cogt.model_routing.routing_profile import RoutingProfile
from pipelex.tools.config.config_model import ConfigModel


class RoutingProfileBlueprint(ConfigModel):
    """Blueprint for creating ModelCatalogConfig instances."""

    description: str
    default: str
    routes: Dict[str, str] = Field(default_factory=dict)


class ModelCatalogBlueprint(ConfigModel):
    """Blueprint for the entire model catalog."""

    active: str
    configs: Dict[str, RoutingProfileBlueprint] = Field(default_factory=dict)


class RoutingProfileFactory:
    """Factory for creating model catalog configurations."""

    @classmethod
    def make_routing_profile(
        cls,
        name: str,
        blueprint: RoutingProfileBlueprint,
    ) -> RoutingProfile:
        """Create a ModelCatalogConfig from a blueprint.

        Args:
            config_blueprint: Blueprint containing configuration data

        Returns:
            ModelCatalogConfig instance
        """
        return RoutingProfile(
            name=name,
            description=blueprint.description,
            default=blueprint.default,
            routes=blueprint.routes,
        )
