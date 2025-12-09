"""Unit tests for PipelexServiceConfig."""

import os
import pathlib
import tempfile

import pytest

from pipelex.system.pipelex_service.pipelex_service_config import (
    PIPELEX_SERVICE_CONFIG_FILE_NAME,
    GatewayConfig,
    PipelexServiceConfig,
    PipelexServiceConfigValidationError,
    load_pipelex_service_config,
    load_pipelex_service_config_if_exists,
)


class TestPipelexServiceConfig:
    """Tests for PipelexServiceConfig and related functions."""

    def test_gateway_config_default_terms_not_accepted(self) -> None:
        """Test that gateway terms_accepted defaults to False."""
        config = GatewayConfig()
        assert config.terms_accepted is False

    def test_gateway_config_terms_accepted(self) -> None:
        """Test gateway config with terms_accepted = True."""
        config = GatewayConfig(terms_accepted=True)
        assert config.terms_accepted is True

    def test_pipelex_service_config_default(self) -> None:
        """Test PipelexServiceConfig with default values."""
        config = PipelexServiceConfig()
        assert config.gateway.terms_accepted is False

    def test_pipelex_service_config_with_gateway(self) -> None:
        """Test PipelexServiceConfig with custom gateway config."""
        config = PipelexServiceConfig(gateway=GatewayConfig(terms_accepted=True))
        assert config.gateway.terms_accepted is True

    def test_load_pipelex_service_config_valid(self) -> None:
        """Test loading a valid pipelex_service.toml file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_content = """[gateway]
terms_accepted = true
"""
            config_path = os.path.join(temp_dir, PIPELEX_SERVICE_CONFIG_FILE_NAME)
            pathlib.Path(config_path).write_text(config_content, encoding="utf-8")

            config = load_pipelex_service_config(config_dir=temp_dir)
            assert config.gateway.terms_accepted is True

    def test_load_pipelex_service_config_not_found(self) -> None:
        """Test loading config from non-existent directory raises FileNotFoundError."""
        with tempfile.TemporaryDirectory() as temp_dir, pytest.raises(FileNotFoundError):
            load_pipelex_service_config(config_dir=temp_dir)

    def test_load_pipelex_service_config_invalid(self) -> None:
        """Test loading an invalid pipelex_service.toml raises validation error."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Invalid TOML - gateway.terms_accepted should be bool, not string
            config_content = """[gateway]
terms_accepted = "invalid"
"""
            config_path = os.path.join(temp_dir, PIPELEX_SERVICE_CONFIG_FILE_NAME)
            pathlib.Path(config_path).write_text(config_content, encoding="utf-8")

            with pytest.raises(PipelexServiceConfigValidationError):
                load_pipelex_service_config(config_dir=temp_dir)

    def test_load_pipelex_service_config_if_exists_returns_none(self) -> None:
        """Test load_pipelex_service_config_if_exists returns None when file doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_pipelex_service_config_if_exists(config_dir=temp_dir)
            assert config is None

    def test_load_pipelex_service_config_if_exists_returns_config(self) -> None:
        """Test load_pipelex_service_config_if_exists returns config when file exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_content = """[gateway]
terms_accepted = false
"""
            config_path = os.path.join(temp_dir, PIPELEX_SERVICE_CONFIG_FILE_NAME)
            pathlib.Path(config_path).write_text(config_content, encoding="utf-8")

            config = load_pipelex_service_config_if_exists(config_dir=temp_dir)
            assert config is not None
            assert config.gateway.terms_accepted is False
