from pipelex.cogt.model_routing.routing_models import BackendMatchingMethod
from pipelex.cogt.model_routing.routing_profile import RoutingProfile
from pipelex.cogt.model_routing.routing_profile_factory import RoutingProfileBlueprint, RoutingProfileFactory


class TestRoutingProfileOptionalRoutes:
    """Tests for optional_routes: factory pass-through and enabled-backend gating."""

    def test_factory_carries_optional_routes_from_blueprint(self):
        """Regression: the factory used to drop optional_routes parsed from the blueprint."""
        # Arrange
        blueprint = RoutingProfileBlueprint(
            description="test profile",
            default="openai",
            optional_routes={"hello-1": "hello"},
        )

        # Act
        routing_profile = RoutingProfileFactory.make_routing_profile(
            name="test_profile",
            blueprint=blueprint,
        )

        # Assert
        assert routing_profile.optional_routes == {"hello-1": "hello"}

    def test_optional_route_applies_when_backend_enabled(self):
        """An optional route wins as an exact match when its target backend is enabled."""
        # Arrange
        routing_profile = RoutingProfile(
            name="test_profile",
            default="openai",
            optional_routes={"hello-1": "hello"},
        )
        enabled_backends = ["openai", "hello"]

        # Act
        result = routing_profile.get_backend_match_for_model(
            enabled_backends=enabled_backends,
            model_name="hello-1",
        )

        # Assert
        assert result is not None
        assert result.backend_name == "hello"
        assert result.matching_method == BackendMatchingMethod.EXACT_MATCH

    def test_optional_route_inert_when_backend_disabled(self):
        """An optional route whose target backend is disabled falls through to the default."""
        # Arrange
        routing_profile = RoutingProfile(
            name="test_profile",
            default="openai",
            optional_routes={"hello-1": "hello"},
        )
        enabled_backends = ["openai"]

        # Act
        result = routing_profile.get_backend_match_for_model(
            enabled_backends=enabled_backends,
            model_name="hello-1",
        )

        # Assert
        assert result is not None
        assert result.backend_name == "openai"
        assert result.matching_method == BackendMatchingMethod.DEFAULT
