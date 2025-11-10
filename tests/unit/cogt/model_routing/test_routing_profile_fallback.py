from pipelex.cogt.model_routing.routing_models import BackendMatchingMethod
from pipelex.cogt.model_routing.routing_profile import RoutingProfile


class TestRoutingProfileFallbackOrder:
    """Tests for the fallback_order functionality in RoutingProfile."""

    def test_fallback_order_used_when_default_not_set(self):
        """Test that fallback_order[0] is used as primary backend when default is not set."""
        # Arrange
        routing_profile = RoutingProfile(
            name="test_profile",
            fallback_order=["openai", "anthropic", "google"],
        )
        enabled_backends = ["openai", "anthropic", "google"]

        # Act
        result = routing_profile.get_backend_match_for_model(
            enabled_backends=enabled_backends,
            model_name="test-model",
        )

        # Assert
        assert result is not None
        assert result.backend_name == "openai"
        assert result.matching_method == BackendMatchingMethod.DEFAULT
        assert result.fallback_order == ["openai", "anthropic", "google"]

    def test_default_used_when_both_default_and_fallback_order_set(self):
        """Test that default is used as primary backend when both default and fallback_order are set."""
        # Arrange
        routing_profile = RoutingProfile(
            name="test_profile",
            default="anthropic",
            fallback_order=["openai", "google"],
        )
        enabled_backends = ["openai", "anthropic", "google"]

        # Act
        result = routing_profile.get_backend_match_for_model(
            enabled_backends=enabled_backends,
            model_name="test-model",
        )

        # Assert
        assert result is not None
        assert result.backend_name == "anthropic"
        assert result.matching_method == BackendMatchingMethod.DEFAULT
        assert result.fallback_order == ["openai", "google"]

    def test_fallback_order_included_in_result_when_default_is_set(self):
        """Test that fallback_order is included in result even when default is used."""
        # Arrange
        routing_profile = RoutingProfile(
            name="test_profile",
            default="openai",
            fallback_order=["anthropic", "google"],
        )
        enabled_backends = ["openai", "anthropic", "google"]

        # Act
        result = routing_profile.get_backend_match_for_model(
            enabled_backends=enabled_backends,
            model_name="test-model",
        )

        # Assert
        assert result is not None
        assert result.backend_name == "openai"
        assert result.fallback_order == ["anthropic", "google"]

    def test_nonexistent_backend_in_fallback_order_is_filtered_out(self):
        """Test that nonexistent backends in fallback_order are silently filtered out."""
        # Arrange
        routing_profile = RoutingProfile(
            name="test_profile",
            fallback_order=["openai", "nonexistent_backend", "google"],
        )
        enabled_backends = ["openai", "google"]

        # Act
        result = routing_profile.get_backend_match_for_model(
            enabled_backends=enabled_backends,
            model_name="test-model",
        )

        # Assert - nonexistent_backend should be filtered out
        assert result is not None
        assert result.backend_name == "openai"  # First enabled backend
        assert result.fallback_order == ["openai", "google"]  # Only enabled backends

    def test_disabled_backend_in_fallback_order_is_filtered_out(self):
        """Test that disabled backends in fallback_order are silently filtered out."""
        # Arrange
        routing_profile = RoutingProfile(
            name="test_profile",
            fallback_order=["openai", "anthropic", "google"],
        )
        enabled_backends = ["openai", "google"]  # anthropic is disabled

        # Act
        result = routing_profile.get_backend_match_for_model(
            enabled_backends=enabled_backends,
            model_name="test-model",
        )

        # Assert - anthropic should be filtered out
        assert result is not None
        assert result.backend_name == "openai"
        assert result.fallback_order == ["openai", "google"]  # Only enabled backends

    def test_current_behavior_preserved_when_neither_default_nor_fallback_order_set(self):
        """Test that None is returned when neither default nor fallback_order is set."""
        # Arrange
        routing_profile = RoutingProfile(
            name="test_profile",
        )
        enabled_backends = ["openai", "anthropic", "google"]

        # Act
        result = routing_profile.get_backend_match_for_model(
            enabled_backends=enabled_backends,
            model_name="test-model",
        )

        # Assert
        assert result is None

    def test_exact_match_takes_precedence_over_fallback_order(self):
        """Test that exact route match takes precedence over fallback_order."""
        # Arrange
        routing_profile = RoutingProfile(
            name="test_profile",
            routes={"test-model": "google"},
            fallback_order=["openai", "anthropic"],
        )
        enabled_backends = ["openai", "anthropic", "google"]

        # Act
        result = routing_profile.get_backend_match_for_model(
            enabled_backends=enabled_backends,
            model_name="test-model",
        )

        # Assert
        assert result is not None
        assert result.backend_name == "google"
        assert result.matching_method == BackendMatchingMethod.EXACT_MATCH
        assert result.fallback_order is None  # Not DEFAULT match, so no fallback_order

    def test_pattern_match_takes_precedence_over_fallback_order(self):
        """Test that pattern match takes precedence over fallback_order."""
        # Arrange
        routing_profile = RoutingProfile(
            name="test_profile",
            routes={"gpt-*": "openai"},
            fallback_order=["anthropic", "google"],
        )
        enabled_backends = ["openai", "anthropic", "google"]

        # Act
        result = routing_profile.get_backend_match_for_model(
            enabled_backends=enabled_backends,
            model_name="gpt-4",
        )

        # Assert
        assert result is not None
        assert result.backend_name == "openai"
        assert result.matching_method == BackendMatchingMethod.PATTERN_MATCH
        assert result.fallback_order is None  # Not DEFAULT match, so no fallback_order

    def test_fallback_order_with_single_backend(self):
        """Test that fallback_order works with a single backend."""
        # Arrange
        routing_profile = RoutingProfile(
            name="test_profile",
            fallback_order=["openai"],
        )
        enabled_backends = ["openai", "anthropic"]

        # Act
        result = routing_profile.get_backend_match_for_model(
            enabled_backends=enabled_backends,
            model_name="test-model",
        )

        # Assert
        assert result is not None
        assert result.backend_name == "openai"
        assert result.fallback_order == ["openai"]

    def test_empty_fallback_order_treated_as_none(self):
        """Test that empty fallback_order is treated as if not set."""
        # Arrange
        routing_profile = RoutingProfile(
            name="test_profile",
            fallback_order=[],
        )
        enabled_backends = ["openai", "anthropic"]

        # Act
        result = routing_profile.get_backend_match_for_model(
            enabled_backends=enabled_backends,
            model_name="test-model",
        )

        # Assert
        assert result is None

    def test_default_not_in_enabled_backends_falls_back_to_fallback_order(self):
        """Test that if default is not in enabled_backends, fallback_order is used."""
        # Arrange
        routing_profile = RoutingProfile(
            name="test_profile",
            default="disabled_backend",
            fallback_order=["openai", "anthropic"],
        )
        enabled_backends = ["openai", "anthropic"]

        # Act
        result = routing_profile.get_backend_match_for_model(
            enabled_backends=enabled_backends,
            model_name="test-model",
        )

        # Assert
        assert result is not None
        assert result.backend_name == "openai"  # First from fallback_order
        assert result.fallback_order == ["openai", "anthropic"]

    def test_fallback_order_filters_disabled_backends(self):
        """Test that disabled backends are filtered out from fallback_order."""
        # Arrange
        routing_profile = RoutingProfile(
            name="test_profile",
            fallback_order=["backend1", "backend2", "backend3"],
        )
        enabled_backends = ["backend1"]

        # Act
        result = routing_profile.get_backend_match_for_model(
            enabled_backends=enabled_backends,
            model_name="test-model",
        )

        # Assert - only enabled backends should remain
        assert result is not None
        assert result.backend_name == "backend1"
        assert result.fallback_order == ["backend1"]  # backend2 and backend3 filtered out

    def test_fallback_order_preserved_in_result(self):
        """Test that the exact fallback_order list is preserved in the result."""
        # Arrange
        fallback_order = ["openai", "anthropic", "google", "mistral"]
        routing_profile = RoutingProfile(
            name="test_profile",
            default="openai",
            fallback_order=fallback_order,
        )
        enabled_backends = ["openai", "anthropic", "google", "mistral"]

        # Act
        result = routing_profile.get_backend_match_for_model(
            enabled_backends=enabled_backends,
            model_name="test-model",
        )

        # Assert
        assert result is not None
        assert result.fallback_order == fallback_order
        assert result.fallback_order is not fallback_order  # Should be a copy/separate reference
