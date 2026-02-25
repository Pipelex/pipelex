import pytest
from pydantic import ValidationError

from pipelex.system.pipelex_service.remote_config import RemoteConfig


class TestRemoteConfig:
    """Tests for GatewayRemoteConfig model."""

    def test_remote_config_valid(self) -> None:
        """Test creating a valid GatewayRemoteConfig."""
        payload = {
            "backend_model_specs": {
                "defaults": {"sdk": "gateway_completions"},
                "gpt-4o": {"model_id": "gpt-4o-2024-11-20"},
            },
            "posthog": {
                "project_api_key": "test-project-api-key",
                "endpoint": "https://test-endpoint.com",
                "is_geoip_enabled": True,
                "is_debug_enabled": False,
            },
        }
        config = RemoteConfig.model_validate(payload)
        assert "defaults" in config.backend_model_specs
        assert "gpt-4o" in config.backend_model_specs

    def test_remote_config_missing_backend_fails(self) -> None:
        """Test that missing backend key raises validation error."""
        payload = {"other_key": "value"}
        with pytest.raises(ValidationError):
            RemoteConfig.model_validate(payload)

    def test_remote_config_empty_backend(self) -> None:
        """Test GatewayRemoteConfig with empty backend dict."""
        payload = {
            "backend_model_specs": {},
            "posthog": {
                "project_api_key": "test-project-api-key",
                "endpoint": "https://test-endpoint.com",
                "is_geoip_enabled": True,
                "is_debug_enabled": False,
            },
        }
        config = RemoteConfig.model_validate(payload)
        assert config.backend_model_specs == {}
