from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.kit.paths import get_kit_configs_dir
from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit


def get_backend_indices_helper(backends_toml_path: str, backend_names: list[str]) -> list[int]:
    """Get 1-based indices for given backend names from backends.toml.

    Args:
        backends_toml_path: Path to backends.toml file.
        backend_names: List of backend keys to find indices for.

    Returns:
        List of 1-based indices corresponding to the backend names.
    """
    toml_doc = load_toml_with_tomlkit(backends_toml_path)
    backend_list: list[str] = [key for key in toml_doc if key != "internal"]
    indices: list[int] = []
    for name in backend_names:
        if name in backend_list:
            # 1-based index for user input
            indices.append(backend_list.index(name) + 1)
    return indices


def verify_backends_toml(backends_toml_path: str, expected_enabled: list[str]) -> None:
    """Verify backends.toml has expected backends enabled.

    Args:
        backends_toml_path: Path to backends.toml file.
        expected_enabled: List of backend keys expected to be enabled.
    """
    toml_doc = load_toml_with_tomlkit(backends_toml_path)

    for backend_key in toml_doc:
        if backend_key == "internal":
            # Internal should always be enabled
            assert toml_doc[backend_key]["enabled"] is True  # type: ignore[index]
        elif backend_key in expected_enabled:
            assert toml_doc[backend_key]["enabled"] is True, f"Expected {backend_key} to be enabled"  # type: ignore[index]
        # Check if enabled field exists before asserting
        elif "enabled" in toml_doc[backend_key]:  # type: ignore[operator]
            assert toml_doc[backend_key]["enabled"] is False, f"Expected {backend_key} to be disabled"  # type: ignore[index]


def verify_routing_profile(
    routing_profiles_toml_path: str,
    expected_active: str,
    expected_default: str | None = None,
    expected_fallback_order: list[str] | None = None,
) -> None:
    """Verify routing_profiles.toml has expected configuration.

    Args:
        routing_profiles_toml_path: Path to routing_profiles.toml file.
        expected_active: Expected active profile name.
        expected_default: Expected default backend (optional).
        expected_fallback_order: Expected fallback order (optional).
    """
    toml_doc = load_toml_with_tomlkit(routing_profiles_toml_path)

    assert toml_doc["active"] == expected_active, f"Expected active profile '{expected_active}', got '{toml_doc['active']}'"

    if expected_default is not None or expected_fallback_order is not None:
        profiles: dict[str, Any] = toml_doc.get("profiles", {})  # type: ignore[assignment]
        assert expected_active in profiles, f"Profile '{expected_active}' not found"

        profile = profiles[expected_active]  # type: ignore[index]

        if expected_default is not None:
            assert profile.get("default") == expected_default, f"Expected default '{expected_default}'"  # type: ignore[union-attr]

        if expected_fallback_order is not None:
            actual_fallback = profile.get("fallback_order")  # type: ignore[union-attr]
            assert actual_fallback == expected_fallback_order, f"Expected fallback_order {expected_fallback_order}, got {actual_fallback}"


def verify_telemetry_config(telemetry_config_path: str, expected_mode: str) -> None:
    """Verify telemetry.toml has expected mode.

    Args:
        telemetry_config_path: Path to telemetry.toml file.
        expected_mode: Expected telemetry mode ("off", "anonymous", or "identified").
    """
    toml_doc = load_toml_with_tomlkit(telemetry_config_path)
    assert toml_doc["telemetry_mode"] == expected_mode, f"Expected telemetry_mode '{expected_mode}', got '{toml_doc['telemetry_mode']}'"


def setup_pipelex_dir(tmp_path: Path, copy_configs: bool = True, copy_backends: bool = True, copy_routing: bool = True) -> Path:
    """Set up a test .pipelex directory structure.

    Args:
        tmp_path: Pytest temporary path fixture.
        copy_configs: Whether to copy config files from kit.
        copy_backends: Whether to copy backends.toml.
        copy_routing: Whether to copy routing_profiles.toml.

    Returns:
        Path to created .pipelex directory.
    """
    pipelex_dir = tmp_path / ".pipelex"
    pipelex_dir.mkdir(exist_ok=True)

    inference_dir = pipelex_dir / "inference"
    inference_dir.mkdir(exist_ok=True)

    kit_configs_dir = Path(str(get_kit_configs_dir()))

    if copy_configs:
        # Copy main pipelex.toml
        if (kit_configs_dir / "pipelex.toml").exists():
            shutil.copy2(kit_configs_dir / "pipelex.toml", pipelex_dir / "pipelex.toml")

    if copy_backends:
        # Copy backends.toml
        backends_source = kit_configs_dir / "inference" / "backends.toml"
        if backends_source.exists():
            shutil.copy2(backends_source, inference_dir / "backends.toml")

    if copy_routing:
        # Copy routing_profiles.toml
        routing_source = kit_configs_dir / "inference" / "routing_profiles.toml"
        if routing_source.exists():
            shutil.copy2(routing_source, inference_dir / "routing_profiles.toml")

    return pipelex_dir


class MockedInitEnvironment:
    """Encapsulates all mocking setup for init command testing.

    This class manages:
    - File system setup (tmp_path, .pipelex directory)
    - Mocking of Console, Prompt, Confirm
    - User input simulation
    - Configuration verification
    """

    def __init__(self, tmp_path: Path, mocker: MockerFixture):
        """Initialize mocked environment.

        Args:
            tmp_path: Pytest temporary path fixture.
            mocker: Pytest mocker fixture.
        """
        self.tmp_path = tmp_path
        self.mocker = mocker
        self.pipelex_dir = tmp_path / ".pipelex"
        self.inference_dir = self.pipelex_dir / "inference"

        # Store mocks for later use
        self.mock_console: Any = None
        self.mock_prompt_ask: Any = None
        self.mock_confirm_ask: Any = None
        self.mock_config_manager: Any = None

        # Input sequences
        self.prompt_inputs: list[str] = []
        self.confirm_inputs: list[bool] = []

    def setup_empty_dir(self) -> None:
        """Set up an empty .pipelex directory structure."""
        self.pipelex_dir.mkdir(exist_ok=True)
        self.inference_dir.mkdir(exist_ok=True)

    def setup_with_configs(self, include_backends: bool = True, include_routing: bool = True, include_telemetry: bool = False) -> None:
        """Set up .pipelex directory with config files from kit.

        Args:
            include_backends: Whether to include backends.toml.
            include_routing: Whether to include routing_profiles.toml.
            include_telemetry: Whether to include telemetry.toml.
        """
        setup_pipelex_dir(
            self.tmp_path,
            copy_configs=True,
            copy_backends=include_backends,
            copy_routing=include_routing,
        )

        if include_telemetry:
            kit_configs_dir = Path(str(get_kit_configs_dir()))
            telemetry_source = kit_configs_dir / "telemetry.toml"
            if telemetry_source.exists():
                shutil.copy2(telemetry_source, self.pipelex_dir / "telemetry.toml")

    def mock_config_manager_paths(self) -> None:
        """Mock config_manager to use tmp_path."""
        self.mock_config_manager = self.mocker.MagicMock()
        self.mock_config_manager.pipelex_config_dir = str(self.pipelex_dir)

        # Patch all locations where config_manager is used
        self.mocker.patch("pipelex.cli.commands.init.command.config_manager", self.mock_config_manager)
        self.mocker.patch("pipelex.cli.commands.init.backends.config_manager", self.mock_config_manager)
        self.mocker.patch("pipelex.cli.commands.init.routing.config_manager", self.mock_config_manager)
        self.mocker.patch("pipelex.cli.commands.init.config_files.config_manager", self.mock_config_manager)

    def mock_console_outputs(self) -> None:
        """Mock Console to suppress output."""
        self.mock_console = self.mocker.patch("pipelex.cli.commands.init.command.Console")
        self.mocker.patch("pipelex.cli.commands.init.backends.Console")
        self.mocker.patch("pipelex.cli.commands.init.routing.Console")
        self.mocker.patch("pipelex.cli.commands.init.telemetry.Console")
        self.mocker.patch("pipelex.cli.commands.init.ui.backends_ui.Console")
        self.mocker.patch("pipelex.cli.commands.init.ui.routing_ui.Console")
        self.mocker.patch("pipelex.cli.commands.init.ui.telemetry_ui.Console")

    def add_prompt_input(self, value: str) -> None:
        """Add a prompt input to the sequence.

        Args:
            value: The input value to simulate.
        """
        self.prompt_inputs.append(value)

    def add_confirm_input(self, value: bool) -> None:
        """Add a confirm input to the sequence.

        Args:
            value: The boolean confirmation to simulate.
        """
        self.confirm_inputs.append(value)

    def setup_mocks(self) -> None:
        """Set up all mocks with configured inputs."""
        self.mock_config_manager_paths()
        self.mock_console_outputs()

        # Mock Prompt.ask with side_effect for sequential inputs
        if self.prompt_inputs:
            self.mock_prompt_ask = self.mocker.patch(
                "rich.prompt.Prompt.ask",
                side_effect=self.prompt_inputs,
            )

        # Mock Confirm.ask with side_effect for sequential inputs
        if self.confirm_inputs:
            self.mock_confirm_ask = self.mocker.patch(
                "rich.prompt.Confirm.ask",
                side_effect=self.confirm_inputs,
            )

        # Mock typer.echo to suppress output
        self.mocker.patch("typer.echo")

    def get_backend_indices(self, backend_names: list[str]) -> list[int]:
        """Get 1-based indices for backend names.

        Args:
            backend_names: List of backend keys.

        Returns:
            List of 1-based indices.
        """
        backends_path = str(self.inference_dir / "backends.toml")
        return get_backend_indices_helper(backends_path, backend_names)

    def verify_backends_enabled(self, expected_enabled: list[str]) -> None:
        """Verify backends.toml has expected backends enabled.

        Args:
            expected_enabled: List of backend keys expected to be enabled.
        """
        backends_path = str(self.inference_dir / "backends.toml")
        verify_backends_toml(backends_path, expected_enabled)

    def verify_routing(
        self,
        expected_active: str,
        expected_default: str | None = None,
        expected_fallback_order: list[str] | None = None,
    ) -> None:
        """Verify routing profile configuration.

        Args:
            expected_active: Expected active profile name.
            expected_default: Expected default backend (optional).
            expected_fallback_order: Expected fallback order (optional).
        """
        routing_path = str(self.inference_dir / "routing_profiles.toml")
        verify_routing_profile(routing_path, expected_active, expected_default, expected_fallback_order)

    def verify_telemetry(self, expected_mode: str) -> None:
        """Verify telemetry configuration.

        Args:
            expected_mode: Expected telemetry mode.
        """
        telemetry_path = str(self.pipelex_dir / "telemetry.toml")
        verify_telemetry_config(telemetry_path, expected_mode)

    def verify_file_exists(self, relative_path: str) -> None:
        """Verify a file exists in the pipelex directory.

        Args:
            relative_path: Path relative to .pipelex directory.
        """
        file_path = self.pipelex_dir / relative_path
        assert file_path.exists(), f"Expected file {file_path} to exist"

    def verify_file_not_exists(self, relative_path: str) -> None:
        """Verify a file does not exist in the pipelex directory.

        Args:
            relative_path: Path relative to .pipelex directory.
        """
        file_path = self.pipelex_dir / relative_path
        assert not file_path.exists(), f"Expected file {file_path} to not exist"
