from typing import Dict, Optional

from pydantic import Field

from pipelex.cogt.model_routing.routing_profile import RoutingProfile
from pipelex.tools.config.config_model import ConfigModel


class RoutingProfileBlueprint(ConfigModel):
    """Blueprint for creating RoutingProfile instances."""

    description: str
    default: Optional[str] = None
    routes: Dict[str, str] = Field(default_factory=dict)


class RoutingProfileLibraryBlueprint(ConfigModel):
    """Blueprint for the entire routing profile library."""

    active: str
    profiles: Dict[str, RoutingProfileBlueprint] = Field(default_factory=dict)


class RoutingProfileFactory:
    """Factory for creating routing profile configurations."""

    @classmethod
    def make_routing_profile(
        cls,
        name: str,
        blueprint: RoutingProfileBlueprint,
    ) -> RoutingProfile:
        """Create a RoutingProfile from a blueprint.

        Args:
            name: Name of the routing profile
            blueprint: Blueprint containing configuration data

        Returns:
            RoutingProfile instance
        """
        return RoutingProfile(
            name=name,
            description=blueprint.description,
            default=blueprint.default,
            routes=blueprint.routes,
        )
