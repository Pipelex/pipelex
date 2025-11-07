from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

from pipelex.config import ConfigPaths
from pipelex.exceptions import PipelexSetupError
from pipelex.pipelex import Pipelex


class TestPipelexCheckInitialization:
    """Test the Pipelex.check_is_initialized classmethod."""

    def test_check_is_initialized_returns_true_when_all_files_exist(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that check_is_initialized returns True when all required files exist."""
        # Setup test directories
        config_dir = tmp_path / ".pipelex" / "inference"
        config_dir.mkdir(parents=True)
        backends_file = config_dir / "backends.toml"
        routing_file = config_dir / "routing_profiles.toml"
        backends_file.write_text("[backends]\nconfig = 'value'")
        routing_file.write_text("[routing]\nconfig = 'value'")

        # Mock ConfigPaths to point to temp directory
        mocker.patch.object(ConfigPaths, "BACKENDS_FILE_PATH", str(backends_file))
        mocker.patch.object(ConfigPaths, "ROUTING_PROFILES_FILE_PATH", str(routing_file))

        # Test
        result = Pipelex.check_is_initialized()

        # Verify
        assert result is True

    def test_check_is_initialized_returns_false_when_backends_missing(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that check_is_initialized returns False when backends.toml is missing."""
        # Setup test directories - only routing file exists
        config_dir = tmp_path / ".pipelex" / "inference"
        config_dir.mkdir(parents=True)
        backends_file = config_dir / "backends.toml"
        routing_file = config_dir / "routing_profiles.toml"
        routing_file.write_text("[routing]\nconfig = 'value'")

        # Mock ConfigPaths to point to temp directory
        mocker.patch.object(ConfigPaths, "BACKENDS_FILE_PATH", str(backends_file))
        mocker.patch.object(ConfigPaths, "ROUTING_PROFILES_FILE_PATH", str(routing_file))

        # Test
        result = Pipelex.check_is_initialized(print_warning_if_not=False)

        # Verify
        assert result is False

    def test_check_is_initialized_returns_false_when_routing_missing(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that check_is_initialized returns False when routing_profiles.toml is missing."""
        # Setup test directories - only backends file exists
        config_dir = tmp_path / ".pipelex" / "inference"
        config_dir.mkdir(parents=True)
        backends_file = config_dir / "backends.toml"
        routing_file = config_dir / "routing_profiles.toml"
        backends_file.write_text("[backends]\nconfig = 'value'")

        # Mock ConfigPaths to point to temp directory
        mocker.patch.object(ConfigPaths, "BACKENDS_FILE_PATH", str(backends_file))
        mocker.patch.object(ConfigPaths, "ROUTING_PROFILES_FILE_PATH", str(routing_file))

        # Test
        result = Pipelex.check_is_initialized(print_warning_if_not=False)

        # Verify
        assert result is False

    def test_check_is_initialized_returns_false_when_all_files_missing(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that check_is_initialized returns False when both required files are missing."""
        # Setup test directories - no files exist
        config_dir = tmp_path / ".pipelex" / "inference"
        config_dir.mkdir(parents=True)
        backends_file = config_dir / "backends.toml"
        routing_file = config_dir / "routing_profiles.toml"

        # Mock ConfigPaths to point to temp directory
        mocker.patch.object(ConfigPaths, "BACKENDS_FILE_PATH", str(backends_file))
        mocker.patch.object(ConfigPaths, "ROUTING_PROFILES_FILE_PATH", str(routing_file))

        # Test
        result = Pipelex.check_is_initialized(print_warning_if_not=False)

        # Verify
        assert result is False

    def test_check_is_initialized_raises_when_not_initialized_and_raise_if_not_true(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that check_is_initialized raises PipelexSetupError when raise_if_not is True and not initialized."""
        # Setup test directories - no files exist
        config_dir = tmp_path / ".pipelex" / "inference"
        config_dir.mkdir(parents=True)
        backends_file = config_dir / "backends.toml"
        routing_file = config_dir / "routing_profiles.toml"

        # Mock ConfigPaths to point to temp directory
        mocker.patch.object(ConfigPaths, "BACKENDS_FILE_PATH", str(backends_file))
        mocker.patch.object(ConfigPaths, "ROUTING_PROFILES_FILE_PATH", str(routing_file))

        # Test and verify exception is raised
        with pytest.raises(PipelexSetupError) as exc_info:
            Pipelex.check_is_initialized(print_warning_if_not=True)

        # Verify error message contents (no longer lists file paths)
        error_msg = str(exc_info.value)
        assert "Pipelex is not initialized" in error_msg
        assert "pipelex init" in error_msg

    def test_check_is_initialized_does_not_raise_when_initialized_and_raise_if_not_true(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that check_is_initialized does not raise when initialized even with raise_if_not=True."""
        # Setup test directories - all files exist
        config_dir = tmp_path / ".pipelex" / "inference"
        config_dir.mkdir(parents=True)
        backends_file = config_dir / "backends.toml"
        routing_file = config_dir / "routing_profiles.toml"
        backends_file.write_text("[backends]\nconfig = 'value'")
        routing_file.write_text("[routing]\nconfig = 'value'")

        # Mock ConfigPaths to point to temp directory
        mocker.patch.object(ConfigPaths, "BACKENDS_FILE_PATH", str(backends_file))
        mocker.patch.object(ConfigPaths, "ROUTING_PROFILES_FILE_PATH", str(routing_file))

        # Test - should not raise
        result = Pipelex.check_is_initialized(print_warning_if_not=True)

        # Verify
        assert result is True

    def test_check_is_initialized_raises_with_only_backends_missing(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test error message when only backends file is missing."""
        # Setup test directories - only routing file exists
        config_dir = tmp_path / ".pipelex" / "inference"
        config_dir.mkdir(parents=True)
        backends_file = config_dir / "backends.toml"
        routing_file = config_dir / "routing_profiles.toml"
        routing_file.write_text("[routing]\nconfig = 'value'")

        # Mock ConfigPaths to point to temp directory
        mocker.patch.object(ConfigPaths, "BACKENDS_FILE_PATH", str(backends_file))
        mocker.patch.object(ConfigPaths, "ROUTING_PROFILES_FILE_PATH", str(routing_file))

        # Test and verify exception is raised
        with pytest.raises(PipelexSetupError) as exc_info:
            Pipelex.check_is_initialized(print_warning_if_not=True)

        # Verify error message contents (no longer lists file paths)
        error_msg = str(exc_info.value)
        assert "Pipelex is not initialized" in error_msg
        assert "pipelex init" in error_msg

    def test_check_is_initialized_raises_with_only_routing_missing(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test error message when only routing file is missing."""
        # Setup test directories - only backends file exists
        config_dir = tmp_path / ".pipelex" / "inference"
        config_dir.mkdir(parents=True)
        backends_file = config_dir / "backends.toml"
        routing_file = config_dir / "routing_profiles.toml"
        backends_file.write_text("[backends]\nconfig = 'value'")

        # Mock ConfigPaths to point to temp directory
        mocker.patch.object(ConfigPaths, "BACKENDS_FILE_PATH", str(backends_file))
        mocker.patch.object(ConfigPaths, "ROUTING_PROFILES_FILE_PATH", str(routing_file))

        # Test and verify exception is raised
        with pytest.raises(PipelexSetupError) as exc_info:
            Pipelex.check_is_initialized(print_warning_if_not=True)

        # Verify error message contents (no longer lists file paths)
        error_msg = str(exc_info.value)
        assert "Pipelex is not initialized" in error_msg
        assert "pipelex init" in error_msg
