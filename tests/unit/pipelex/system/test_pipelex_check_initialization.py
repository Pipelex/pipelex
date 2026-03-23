from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from pytest_mock import MockerFixture

from pipelex.system.configuration.config_check import CONFIG_NAME, PLXT_CONFIG_NAME, check_is_initialized


def _make_resolve_config_file(config_dir: Path) -> Callable[[str], Path]:
    def resolve_config_file(name: str) -> Path:
        return config_dir / name

    return resolve_config_file


class TestPipelexCheckInitialization:
    """Test the check_is_initialized function from config_check module."""

    def _setup_config_dir(self, tmp_path: Path, *, config_files: bool = False) -> Path:
        """Create the config directory structure and optionally create config files."""
        config_dir = tmp_path / ".pipelex"
        inference_dir = config_dir / "inference"
        inference_dir.mkdir(parents=True)
        if config_files:
            (config_dir / CONFIG_NAME).write_text("[pipelex]\n")
            (config_dir / PLXT_CONFIG_NAME).write_text("[plxt]\n")
        return config_dir

    def _mock_config_manager_paths(self, mocker: MockerFixture, config_dir: Path, backends_file: str, routing_file: str) -> None:
        """Mock config_manager properties used by config_check."""
        mock_manager = mocker.MagicMock()
        mock_manager.backends_file_path = backends_file
        mock_manager.routing_profiles_file_path = routing_file
        mock_manager.resolve_config_file = _make_resolve_config_file(config_dir)
        mocker.patch("pipelex.system.configuration.config_check.config_manager", mock_manager)

    def test_check_is_initialized_returns_true_when_all_files_exist(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that check_is_initialized returns True when all required files exist."""
        config_dir = self._setup_config_dir(tmp_path, config_files=True)
        inference_dir = config_dir / "inference"
        backends_file = inference_dir / "backends.toml"
        routing_file = inference_dir / "routing_profiles.toml"
        backends_file.write_text("[backends]\nconfig = 'value'")
        routing_file.write_text("[routing]\nconfig = 'value'")

        self._mock_config_manager_paths(mocker, config_dir, str(backends_file), str(routing_file))

        result = check_is_initialized()

        assert result is True

    def test_check_is_initialized_returns_false_when_backends_missing(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that check_is_initialized returns False when backends.toml is missing."""
        config_dir = self._setup_config_dir(tmp_path, config_files=True)
        inference_dir = config_dir / "inference"
        backends_file = inference_dir / "backends.toml"
        routing_file = inference_dir / "routing_profiles.toml"
        routing_file.write_text("[routing]\nconfig = 'value'")

        self._mock_config_manager_paths(mocker, config_dir, str(backends_file), str(routing_file))

        result = check_is_initialized(print_warning_if_not=False)

        assert result is False

    def test_check_is_initialized_returns_false_when_routing_missing(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that check_is_initialized returns False when routing_profiles.toml is missing."""
        config_dir = self._setup_config_dir(tmp_path, config_files=True)
        inference_dir = config_dir / "inference"
        backends_file = inference_dir / "backends.toml"
        routing_file = inference_dir / "routing_profiles.toml"
        backends_file.write_text("[backends]\nconfig = 'value'")

        self._mock_config_manager_paths(mocker, config_dir, str(backends_file), str(routing_file))

        result = check_is_initialized(print_warning_if_not=False)

        assert result is False

    def test_check_is_initialized_returns_false_when_all_files_missing(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that check_is_initialized returns False when all required files are missing."""
        config_dir = self._setup_config_dir(tmp_path, config_files=False)
        inference_dir = config_dir / "inference"
        backends_file = inference_dir / "backends.toml"
        routing_file = inference_dir / "routing_profiles.toml"

        self._mock_config_manager_paths(mocker, config_dir, str(backends_file), str(routing_file))

        result = check_is_initialized(print_warning_if_not=False)

        assert result is False

    def test_check_is_initialized_prints_warning_when_not_initialized(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that check_is_initialized prints warning and returns False when not initialized and print_warning_if_not is True."""
        config_dir = self._setup_config_dir(tmp_path, config_files=False)
        inference_dir = config_dir / "inference"
        backends_file = inference_dir / "backends.toml"
        routing_file = inference_dir / "routing_profiles.toml"

        self._mock_config_manager_paths(mocker, config_dir, str(backends_file), str(routing_file))

        mock_console = mocker.MagicMock()
        mocker.patch("pipelex.system.configuration.config_check.get_console", return_value=mock_console)

        result = check_is_initialized(print_warning_if_not=True)

        assert result is False
        assert mock_console.print.called

    def test_check_is_initialized_returns_true_when_initialized_with_print_warning(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that check_is_initialized returns True when initialized with print_warning_if_not=True."""
        config_dir = self._setup_config_dir(tmp_path, config_files=True)
        inference_dir = config_dir / "inference"
        backends_file = inference_dir / "backends.toml"
        routing_file = inference_dir / "routing_profiles.toml"
        backends_file.write_text("[backends]\nconfig = 'value'")
        routing_file.write_text("[routing]\nconfig = 'value'")

        self._mock_config_manager_paths(mocker, config_dir, str(backends_file), str(routing_file))

        result = check_is_initialized(print_warning_if_not=True)

        assert result is True

    def test_check_is_initialized_returns_false_with_only_backends_missing(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that check_is_initialized returns False when only backends file is missing."""
        config_dir = self._setup_config_dir(tmp_path, config_files=True)
        inference_dir = config_dir / "inference"
        backends_file = inference_dir / "backends.toml"
        routing_file = inference_dir / "routing_profiles.toml"
        routing_file.write_text("[routing]\nconfig = 'value'")

        self._mock_config_manager_paths(mocker, config_dir, str(backends_file), str(routing_file))
        mocker.patch("pipelex.system.configuration.config_check.get_console", return_value=mocker.MagicMock())

        result = check_is_initialized(print_warning_if_not=True)

        assert result is False

    def test_check_is_initialized_returns_false_with_only_routing_missing(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that check_is_initialized returns False when only routing file is missing."""
        config_dir = self._setup_config_dir(tmp_path, config_files=True)
        inference_dir = config_dir / "inference"
        backends_file = inference_dir / "backends.toml"
        routing_file = inference_dir / "routing_profiles.toml"
        backends_file.write_text("[backends]\nconfig = 'value'")

        self._mock_config_manager_paths(mocker, config_dir, str(backends_file), str(routing_file))
        mocker.patch("pipelex.system.configuration.config_check.get_console", return_value=mocker.MagicMock())

        result = check_is_initialized(print_warning_if_not=True)

        assert result is False
