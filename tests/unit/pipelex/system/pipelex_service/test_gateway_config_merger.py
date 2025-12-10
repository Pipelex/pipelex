"""Unit tests for GatewayConfigMerger."""

import warnings
from typing import Any

import pytest

from pipelex.system.pipelex_service.exceptions import GatewayConfigMergeError, GatewayOverrideWarning
from pipelex.system.pipelex_service.gateway_config_merger import (
    ALLOWED_OVERRIDE_KEYS,
    GatewayConfigMerger,
)


class TestGatewayConfigMerger:
    """Tests for GatewayConfigMerger."""

    def test_merge_no_overrides(self) -> None:
        """Test merging with empty local overrides returns copy of remote config."""
        remote_config: dict[str, Any] = {
            "defaults": {"sdk": "gateway_completions"},
            "gpt-4o": {"model_id": "gpt-4o-2024-11-20", "sdk": "gateway_responses"},
        }
        local_overrides: dict[str, Any] = {}

        result = GatewayConfigMerger.merge(remote_config, local_overrides)

        assert result == remote_config
        # Verify it's a copy, not the same object
        assert result is not remote_config

    def test_merge_allowed_override_applied(self) -> None:
        """Test that allowed keys (sdk, structure_method) are applied."""
        remote_config: dict[str, Any] = {
            "gpt-4o": {
                "model_id": "gpt-4o-2024-11-20",
                "sdk": "gateway_completions",
                "structure_method": "instructor/openai_tools",
            },
        }
        local_overrides: dict[str, Any] = {
            "gpt-4o": {
                "sdk": "gateway_responses",
                "structure_method": "instructor/openai_responses_tools",
            },
        }

        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            result = GatewayConfigMerger.merge(remote_config, local_overrides)

        assert result["gpt-4o"]["sdk"] == "gateway_responses"
        assert result["gpt-4o"]["structure_method"] == "instructor/openai_responses_tools"
        # Original model_id should be preserved
        assert result["gpt-4o"]["model_id"] == "gpt-4o-2024-11-20"
        # Check warning was issued
        assert any(issubclass(warning.category, GatewayOverrideWarning) for warning in caught_warnings)

    def test_merge_disallowed_override_ignored(self) -> None:
        """Test that non-allowed keys are ignored."""
        remote_config: dict[str, Any] = {
            "gpt-4o": {
                "model_id": "gpt-4o-2024-11-20",
                "costs": {"input": 2.5, "output": 10.0},
            },
        }
        local_overrides: dict[str, Any] = {
            "gpt-4o": {
                "model_id": "hacked-model",  # Should be ignored
                "costs": {"input": 0, "output": 0},  # Should be ignored
            },
        }

        result = GatewayConfigMerger.merge(remote_config, local_overrides)

        # Original values should be preserved
        assert result["gpt-4o"]["model_id"] == "gpt-4o-2024-11-20"
        assert result["gpt-4o"]["costs"] == {"input": 2.5, "output": 10.0}

    def test_merge_unknown_model_override_ignored(self) -> None:
        """Test that overrides for unknown models are ignored."""
        remote_config: dict[str, Any] = {
            "gpt-4o": {"model_id": "gpt-4o-2024-11-20"},
        }
        local_overrides: dict[str, Any] = {
            "unknown-model": {"sdk": "gateway_responses"},
        }

        result = GatewayConfigMerger.merge(remote_config, local_overrides)

        # Unknown model should not be added
        assert "unknown-model" not in result

    def test_merge_defaults_override_ignored(self) -> None:
        """Test that defaults section overrides are ignored (only per-model overrides allowed)."""
        remote_config: dict[str, Any] = {
            "defaults": {
                "sdk": "gateway_completions",
                "structure_method": "instructor/openai_tools",
            },
        }
        local_overrides: dict[str, Any] = {
            "defaults": {
                "sdk": "gateway_responses",  # Should be ignored
            },
        }

        result = GatewayConfigMerger.merge(remote_config, local_overrides)

        # Defaults override should be ignored - original values preserved
        assert result["defaults"]["sdk"] == "gateway_completions"
        assert result["defaults"]["structure_method"] == "instructor/openai_tools"

    def test_deep_copy_preserves_nested_dicts(self) -> None:
        """Test that deep copy properly copies nested dictionaries."""
        remote_config: dict[str, Any] = {
            "gpt-4o": {
                "model_id": "gpt-4o",
                "costs": {"input": 2.5, "output": 10.0},
                "inputs": ["text", "images"],
            },
        }

        result = GatewayConfigMerger.merge(remote_config, {})

        # Modify the result
        result["gpt-4o"]["costs"]["input"] = 999

        # Original should be unchanged
        assert remote_config["gpt-4o"]["costs"]["input"] == 2.5

    def test_allowed_override_keys_contains_expected(self) -> None:
        """Test that ALLOWED_OVERRIDE_KEYS contains the expected keys."""
        assert "sdk" in ALLOWED_OVERRIDE_KEYS
        assert "structure_method" in ALLOWED_OVERRIDE_KEYS
        assert len(ALLOWED_OVERRIDE_KEYS) == 2

    def test_merge_with_non_dict_local_override_raises(self) -> None:
        """Test that non-dict local override values raise GatewayConfigMergeError."""
        remote_config: dict[str, Any] = {
            "gpt-4o": {"model_id": "gpt-4o-2024-11-20"},
        }
        local_overrides: dict[str, Any] = {
            "gpt-4o": "not-a-dict",
        }

        with pytest.raises(GatewayConfigMergeError) as exc_info:
            GatewayConfigMerger.merge(remote_config, local_overrides)

        assert "gpt-4o" in str(exc_info.value)
        assert "must be a dictionary" in str(exc_info.value)

    def test_merge_with_non_dict_remote_config_raises(self) -> None:
        """Test that non-dict remote config values raise GatewayConfigMergeError."""
        remote_config: dict[str, Any] = {
            "gpt-4o": "not-a-dict",
        }
        local_overrides: dict[str, Any] = {
            "gpt-4o": {"sdk": "gateway_responses"},
        }

        with pytest.raises(GatewayConfigMergeError) as exc_info:
            GatewayConfigMerger.merge(remote_config, local_overrides)

        assert "gpt-4o" in str(exc_info.value)
        assert "must be a dictionary" in str(exc_info.value)
