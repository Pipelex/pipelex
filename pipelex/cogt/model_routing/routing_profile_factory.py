from pydantic import Field, model_validator

from pipelex.cogt.exceptions import RoutingProfileBlueprintValueError
from pipelex.cogt.model_routing.routing_profile import RoutingProfile
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.types import Self


class RoutingProfileBlueprint(ConfigModel):
    """Blueprint for creating RoutingProfile instances."""

    description: str
    default: str | None = None
    routes: dict[str, str] = Field(default_factory=dict)
    optional_routes: dict[str, str] = Field(default_factory=dict)
    fallback_order: list[str] | None = None

    @model_validator(mode="after")
    def validate_routes(self) -> Self:
        for pattern in self.optional_routes:
            if pattern in self.routes:
                msg = f"Pattern '{pattern}' is both in routes and optional_routes"
                raise RoutingProfileBlueprintValueError(msg)
        return self


class RoutingProfileLibraryBlueprint(ConfigModel):
    """Blueprint for the entire routing profile library."""

    active: str
    profiles: dict[str, RoutingProfileBlueprint] = Field(default_factory=dict)


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
            fallback_order=blueprint.fallback_order,
        )
