"""Unit tests for remote config provider."""

import hashlib

import pytest
from pydantic import ValidationError

from pipelex.system.pipelex_service.remote_config_provider import GatewayRemoteConfig


class TestGatewayRemoteConfig:
    """Tests for GatewayRemoteConfig model."""

    def test_gateway_remote_config_valid(self) -> None:
        """Test creating a valid GatewayRemoteConfig."""
        payload = {
            "backend": {
                "defaults": {"sdk": "gateway_completions"},
                "gpt-4o": {"model_id": "gpt-4o-2024-11-20"},
            }
        }
        config = GatewayRemoteConfig.model_validate(payload)
        assert "defaults" in config.backend
        assert "gpt-4o" in config.backend

    def test_gateway_remote_config_missing_backend_fails(self) -> None:
        """Test that missing backend key raises validation error."""
        payload = {"other_key": "value"}
        with pytest.raises(ValidationError):
            GatewayRemoteConfig.model_validate(payload)

    def test_gateway_remote_config_empty_backend(self) -> None:
        """Test GatewayRemoteConfig with empty backend dict."""
        payload: dict[str, dict[str, str]] = {"backend": {}}
        config = GatewayRemoteConfig.model_validate(payload)
        assert config.backend == {}


class TestApiKeyHashing:
    """Tests for API key hashing functionality.

    The hash is used as distinct_id for Pipelex PostHog telemetry.
    """

    @staticmethod
    def _hash_api_key(api_key: str) -> str:
        """Hash the API key using SHA256 - same logic as hash_gateway_api_key."""
        return hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    def test_hash_api_key_deterministic(self) -> None:
        """Test that API key hashing is deterministic."""
        api_key = "test-api-key-123"
        hash1 = self._hash_api_key(api_key)
        hash2 = self._hash_api_key(api_key)
        assert hash1 == hash2

    def test_hash_api_key_different_keys(self) -> None:
        """Test that different API keys produce different hashes."""
        hash1 = self._hash_api_key("key1")
        hash2 = self._hash_api_key("key2")
        assert hash1 != hash2

    def test_hash_api_key_is_sha256(self) -> None:
        """Test that hash is 64 characters (SHA256 hex)."""
        api_key = "test-key"
        hashed = self._hash_api_key(api_key)
        assert len(hashed) == 64
        # Verify it's a valid hex string
        int(hashed, 16)
