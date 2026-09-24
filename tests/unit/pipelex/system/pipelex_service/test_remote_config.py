from typing import Any

from pipelex.cogt.model_backends.backend import MANIFOLD_MODEL_SPECS_SECTION
from pipelex.system.pipelex_service.remote_config import RemoteConfig


class TestRemoteConfig:
    """Tests for the RemoteConfig model."""

    def test_remote_config_carries_its_sections_as_extras(self) -> None:
        """The artifact declares no field of its own: every section arrives through `extra="allow"`."""
        payload: dict[str, Any] = {
            MANIFOLD_MODEL_SPECS_SECTION: {
                "defaults": {"sdk": "manifold_completions"},
                "gpt-4o": {"model_id": "gpt-4o-2024-11-20"},
            },
            "aws_region": "us-east-1",
        }
        config = RemoteConfig.model_validate(payload)
        section = config.get_model_specs_section(MANIFOLD_MODEL_SPECS_SECTION)
        assert section is not None
        assert "defaults" in section
        assert "gpt-4o" in section

    def test_remote_config_tolerates_keys_it_does_not_read(self) -> None:
        """The artifact is shared with other consumers, so a key the runtime never asks for is not a refusal."""
        payload: dict[str, Any] = {"other_key": "value"}
        config = RemoteConfig.model_validate(payload)
        assert config.get_model_specs_section(MANIFOLD_MODEL_SPECS_SECTION) is None

    def test_remote_config_empty_section(self) -> None:
        payload: dict[str, Any] = {MANIFOLD_MODEL_SPECS_SECTION: {}}
        config = RemoteConfig.model_validate(payload)
        assert config.get_model_specs_section(MANIFOLD_MODEL_SPECS_SECTION) == {}
