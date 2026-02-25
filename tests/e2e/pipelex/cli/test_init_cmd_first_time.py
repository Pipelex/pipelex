from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import typer

from pipelex.cli.commands.init.command import init_cmd
from pipelex.cli.commands.init.ui.types import InitFocus
from pipelex.cogt.model_backends.backend import PipelexBackend
from pipelex.cogt.model_routing.routing_profile import PipelexRoutingProfile
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit
from tests.helpers.init_cmd_helpers import MockedInitEnvironment, get_backend_indices_helper

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestFirstTimeInitialization:
    def test_complete_init_with_default_selections(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 1.1: Complete initialization with default selections."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # User inputs: confirm init, default backend (1), accept gateway terms
        env.add_confirm_input(True)  # Confirm initialization
        env.add_confirm_input(True)  # Accept gateway terms of service
        env.add_prompt_input("1")  # Default: pipelex_gateway

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL)

        # Verify
        env.verify_file_exists("pipelex.toml")
        env.verify_file_exists("inference/backends.toml")
        env.verify_file_exists("inference/routing_profiles.toml")
        env.verify_file_exists("telemetry.toml")
        env.verify_backends_enabled([PipelexBackend.GATEWAY])
        env.verify_routing(PipelexRoutingProfile.ALL_PIPELEX_GATEWAY)
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

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL)

        # Verify backends
        env.verify_backends_enabled(["openai", "anthropic", "mistral"])

        # Verify custom routing
        env.verify_routing("custom_routing", expected_default="anthropic")

        # Verify telemetry (default mode from template)
        env.verify_telemetry("off")

    def test_init_with_all_backends(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 1.3: Initialization with all backends."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # User inputs
        env.add_confirm_input(True)  # Confirm initialization
        env.add_confirm_input(True)  # Accept gateway terms of service (since all includes gateway)
        env.add_prompt_input("all")  # Select all backends

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL)

        # Verify all backends are enabled
        toml_doc = load_toml_with_tomlkit(str(env.inference_dir / "backends.toml"))
        for backend_key in toml_doc:
            if backend_key != "internal":
                assert toml_doc[backend_key]["enabled"] is True  # type: ignore[index]

        # Verify routing (all_pipelex_gateway since pipelex_gateway is included)
        env.verify_routing(PipelexRoutingProfile.ALL_PIPELEX_GATEWAY)

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
            init_cmd(focus=InitFocus.ALL)
        except (typer.Exit, SystemExit):
            # Expected: user quit at backend selection
            pass

        # Verify config files were created but backends remain in template state
        env.verify_file_exists("inference/backends.toml")

        # Verify pipelex_gateway is still enabled (default template state)
        toml_doc = load_toml_with_tomlkit(str(env.inference_dir / "backends.toml"))
        assert toml_doc[PipelexBackend.GATEWAY]["enabled"] is True  # type: ignore[index]

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
            init_cmd(focus=InitFocus.ALL)

        # Verify no files were created
        env.verify_file_not_exists("pipelex.toml")
        env.verify_file_not_exists("inference/backends.toml")
