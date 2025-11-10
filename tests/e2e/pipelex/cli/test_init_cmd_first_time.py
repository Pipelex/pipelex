from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import typer

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cli.commands.init.command import init_cmd
from pipelex.cli.commands.init.ui.types import InitFocus
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit
from tests.helpers.init_cmd_helpers import MockedInitEnvironment, get_backend_indices_helper


class TestFirstTimeInitialization:
    def test_complete_init_with_default_selections(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 1.1: Complete initialization with default selections."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # User inputs: confirm, default backend (1), telemetry OFF (1)
        env.add_confirm_input(True)
        env.add_prompt_input("1")  # Default: pipelex_inference
        env.add_prompt_input("1")  # Telemetry: OFF

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL, reset=False)

        # Verify
        env.verify_file_exists("pipelex.toml")
        env.verify_file_exists("inference/backends.toml")
        env.verify_file_exists("inference/routing_profiles.toml")
        env.verify_file_exists("telemetry.toml")
        env.verify_backends_enabled(["pipelex_inference"])
        env.verify_routing("pipelex_first")
        env.verify_telemetry("off")

    def test_init_with_multiple_backends_and_routing(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 1.2: Initialization with multiple backends."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # Get indices for anthropic, mistral, openai (in this order for testing)
        kit_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        indices = get_backend_indices_helper(str(kit_backends), ["anthropic", "mistral", "openai"])
        indices_str = ",".join(str(i) for i in indices)

        # User inputs
        env.add_confirm_input(True)  # Confirm initialization
        env.add_prompt_input(indices_str)  # Select 3 backends
        env.add_prompt_input("1")  # Primary: first one (anthropic)
        env.add_prompt_input("2,1")  # Custom fallback order (mistral, anthropic)
        env.add_prompt_input("2")  # Telemetry: ANONYMOUS

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL, reset=False)

        # Verify backends
        env.verify_backends_enabled(["openai", "anthropic", "mistral"])

        # Verify custom routing
        env.verify_routing("custom_routing", expected_default="anthropic")

        # Verify telemetry
        env.verify_telemetry("anonymous")

    def test_init_with_all_backends(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 1.3: Initialization with all backends."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # User inputs
        env.add_confirm_input(True)  # Confirm initialization
        env.add_prompt_input("all")  # Select all backends
        env.add_prompt_input("1")  # Telemetry: OFF

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL, reset=False)

        # Verify all backends are enabled
        toml_doc = load_toml_with_tomlkit(str(env.inference_dir / "backends.toml"))
        for backend_key in toml_doc:
            if backend_key != "internal":
                assert toml_doc[backend_key]["enabled"] is True  # type: ignore[index]

        # Verify routing (pipelex_first since pipelex_inference is included)
        env.verify_routing("pipelex_first")

    def test_cancel_at_backend_selection(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 1.4: Cancel at backend selection."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # User inputs: confirm, then quit at backend selection
        env.add_confirm_input(True)  # Confirm initialization
        env.add_prompt_input("q")  # Quit at backend selection

        env.setup_mocks()

        # Execute - may raise an exit exception on cancellation
        try:
            init_cmd(focus=InitFocus.ALL, reset=False)
        except (typer.Exit, SystemExit):
            # Expected: user quit at backend selection
            pass

        # Verify config files were created but backends remain in template state
        env.verify_file_exists("inference/backends.toml")

        # Verify pipelex_inference is still enabled (default template state)
        toml_doc = load_toml_with_tomlkit(str(env.inference_dir / "backends.toml"))
        assert toml_doc["pipelex_inference"]["enabled"] is True  # type: ignore[index]

    def test_cancel_at_initialization_confirmation(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 1.5: Cancel at initialization confirmation."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # User inputs: decline confirmation
        env.add_confirm_input(False)  # Decline initialization

        env.setup_mocks()

        # Execute - should raise typer.Exit
        with pytest.raises(typer.Exit):
            init_cmd(focus=InitFocus.ALL, reset=False)

        # Verify no files were created
        env.verify_file_not_exists("pipelex.toml")
        env.verify_file_not_exists("inference/backends.toml")
