from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

from pipelex.config import ConfigPaths
from pipelex.system.configuration.config_check import check_is_initialized


class TestPipelexCheckInitialization:
    """Test the check_is_initialized function from config_check module."""

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
        result = check_is_initialized()

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
        result = check_is_initialized(print_warning_if_not=False)

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
        result = check_is_initialized(print_warning_if_not=False)

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
        result = check_is_initialized(print_warning_if_not=False)

        # Verify
        assert result is False

    def test_check_is_initialized_prints_warning_when_not_initialized(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that check_is_initialized prints warning and returns False when not initialized and print_warning_if_not is True."""
        # Setup test directories - no files exist
        config_dir = tmp_path / ".pipelex" / "inference"
        config_dir.mkdir(parents=True)
        backends_file = config_dir / "backends.toml"
        routing_file = config_dir / "routing_profiles.toml"

        # Mock ConfigPaths to point to temp directory
        mocker.patch.object(ConfigPaths, "BACKENDS_FILE_PATH", str(backends_file))
        mocker.patch.object(ConfigPaths, "ROUTING_PROFILES_FILE_PATH", str(routing_file))

        # Mock console.print to suppress output during test
        mock_console_print = mocker.patch("pipelex.system.configuration.config_check.Console.print")

        # Test - should print warning and return False
        result = check_is_initialized(print_warning_if_not=True)

        # Verify
        assert result is False
        assert mock_console_print.called

    def test_check_is_initialized_returns_true_when_initialized_with_print_warning(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that check_is_initialized returns True when initialized with print_warning_if_not=True."""
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

        # Test
        result = check_is_initialized(print_warning_if_not=True)

        # Verify
        assert result is True

    def test_check_is_initialized_returns_false_with_only_backends_missing(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that check_is_initialized returns False when only backends file is missing."""
        # Setup test directories - only routing file exists
        config_dir = tmp_path / ".pipelex" / "inference"
        config_dir.mkdir(parents=True)
        backends_file = config_dir / "backends.toml"
        routing_file = config_dir / "routing_profiles.toml"
        routing_file.write_text("[routing]\nconfig = 'value'")

        # Mock ConfigPaths to point to temp directory
        mocker.patch.object(ConfigPaths, "BACKENDS_FILE_PATH", str(backends_file))
        mocker.patch.object(ConfigPaths, "ROUTING_PROFILES_FILE_PATH", str(routing_file))

        # Mock console.print to suppress output during test
        mocker.patch("pipelex.system.configuration.config_check.Console.print")

        # Test
        result = check_is_initialized(print_warning_if_not=True)

        # Verify
        assert result is False

    def test_check_is_initialized_returns_false_with_only_routing_missing(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that check_is_initialized returns False when only routing file is missing."""
        # Setup test directories - only backends file exists
        config_dir = tmp_path / ".pipelex" / "inference"
        config_dir.mkdir(parents=True)
        backends_file = config_dir / "backends.toml"
        routing_file = config_dir / "routing_profiles.toml"
        backends_file.write_text("[backends]\nconfig = 'value'")

        # Mock ConfigPaths to point to temp directory
        mocker.patch.object(ConfigPaths, "BACKENDS_FILE_PATH", str(backends_file))
        mocker.patch.object(ConfigPaths, "ROUTING_PROFILES_FILE_PATH", str(routing_file))

        # Mock console.print to suppress output during test
        mocker.patch("pipelex.system.configuration.config_check.Console.print")

        # Test
        result = check_is_initialized(print_warning_if_not=True)

        # Verify
        assert result is False
