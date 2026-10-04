"""Unit tests for PipelexServiceConfig."""

import pathlib
import tempfile

from pipelex.system.pipelex_service.pipelex_service_config import (
    PIPELEX_SERVICE_CONFIG_FILE_NAME,
    PipelexServiceConfig,
    load_pipelex_service_config_if_exists,
)
from pipelex.system.pipelex_service.pipelex_service_onboarding import PipelexServiceOnboarding


class TestPipelexServiceConfig:
    """Tests for PipelexServiceConfig and related functions."""

    def test_onboarding_defaults_to_not_completed(self) -> None:
        config = PipelexServiceOnboarding()
        assert config.inference_setup_completed is False

    def test_pipelex_service_config_with_onboarding(self) -> None:
        config = PipelexServiceConfig(onboarding=PipelexServiceOnboarding(inference_setup_completed=True))
        assert config.onboarding.inference_setup_completed is True

    def test_load_pipelex_service_config_if_exists_returns_none(self) -> None:
        """Test load_pipelex_service_config_if_exists returns None when file doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_pipelex_service_config_if_exists(config_dir=pathlib.Path(temp_dir))
            assert config is None

    def test_load_pipelex_service_config_if_exists_returns_config(self) -> None:
        """Test load_pipelex_service_config_if_exists returns config when file exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_content = """[onboarding]
inference_setup_completed = false
"""
            config_path = pathlib.Path(temp_dir) / PIPELEX_SERVICE_CONFIG_FILE_NAME
            config_path.write_text(config_content, encoding="utf-8")

            config = load_pipelex_service_config_if_exists(config_dir=pathlib.Path(temp_dir))
            assert config is not None
            assert config.onboarding.inference_setup_completed is False
