from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pipelex.cli.commands.init.command import init_cmd
from pipelex.cli.commands.init.ui.types import InitFocus
from pipelex.cogt.model_backends.backend import PipelexBackend
from pipelex.cogt.model_routing.routing_profile import PipelexRoutingProfile
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit, save_toml_to_path
from tests.helpers.init_cmd_helpers import MockedInitEnvironment, get_backend_indices_helper

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestFocusedInitialization:
    def test_config_only_initialization(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 2.1: Initialize config files only."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # User inputs
        env.add_confirm_input(True)  # Confirm initialization
        env.add_confirm_input(True)  # Accept gateway terms of service
        env.add_prompt_input("1")  # Backend selection (pipelex_gateway)

        env.setup_mocks()

        # Execute with CONFIG focus
        init_cmd(focus=InitFocus.CONFIG)

        # Verify config files exist
        env.verify_file_exists("pipelex.toml")
        env.verify_file_exists("inference/backends.toml")

    def test_inference_with_existing_config(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 3.1: Initialize inference with existing config."""
        # Setup environment with existing config
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_with_configs(include_backends=True, include_routing=True, include_telemetry=False)

        # Get indices for anthropic and openai
        kit_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        indices = get_backend_indices_helper(str(kit_backends), ["anthropic", "openai"])
        indices_str = ",".join(str(i) for i in indices)

        # User inputs - need to confirm reconfigure since backends already exist
        env.add_confirm_input(True)  # Confirm reconfigure
        env.add_prompt_input(indices_str)  # Select 2 backends
        env.add_prompt_input("1")  # Primary backend (anthropic - first in selection)

        env.setup_mocks()

        # Execute with INFERENCE focus
        init_cmd(focus=InitFocus.INFERENCE)

        # Verify backends are enabled
        env.verify_backends_enabled(["openai", "anthropic"])

        # Verify routing is configured
        env.verify_routing("custom_routing", expected_default="anthropic")

        # Verify NO telemetry prompt appeared
        env.verify_file_not_exists("telemetry.toml")

    def test_reconfigure_inference(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 3.3: Inference already configured - reconfigure."""
        # Setup environment with existing config
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_with_configs(include_backends=True, include_routing=True, include_telemetry=True)

        # Set pipelex_gateway as initially enabled
        backends_path = env.inference_dir / "backends.toml"
        toml_doc = load_toml_with_tomlkit(str(backends_path))
        toml_doc[PipelexBackend.GATEWAY]["enabled"] = True  # type: ignore[index]
        save_toml_to_path(toml_doc, path=str(backends_path))

        # Get index for mistral
        kit_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        indices = get_backend_indices_helper(str(kit_backends), ["mistral"])

        # User inputs
        env.add_confirm_input(True)  # Confirm reconfigure
        env.add_prompt_input(str(indices[0]))  # Change to mistral
        env.add_confirm_input(True)  # Confirm creating profile if needed

        env.setup_mocks()

        # Execute with INFERENCE focus
        init_cmd(focus=InitFocus.INFERENCE)

        # Verify backend was changed
        env.verify_backends_enabled(["mistral"])

        # Verify routing was updated
        env.verify_routing("all_mistral")

    def test_configure_routing_with_multiple_backends(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 4.1: Configure routing with multiple backends enabled."""
        # Setup environment with existing config and multiple backends enabled
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_with_configs(include_backends=True, include_routing=True, include_telemetry=True)

        # Enable multiple backends (anthropic, mistral, openai - in TOML order)
        # Disable all the others so we precisely control the selections
        backends_path = env.inference_dir / "backends.toml"
        toml_doc = load_toml_with_tomlkit(str(backends_path))
        enabled_set = {"anthropic", "mistral", "openai"}
        for backend_key in toml_doc:
            if backend_key == "internal":
                continue
            toml_doc[backend_key]["enabled"] = backend_key in enabled_set  # type: ignore[index]
        save_toml_to_path(toml_doc, path=str(backends_path))

        # User inputs for routing - need to confirm reconfigure since routing already exists
        env.add_confirm_input(True)  # Confirm "Would you like to reconfigure routing?"
        env.add_confirm_input(True)  # Confirm "Continue with initialization?"
        # The backends are enabled and will be listed as: anthropic, mistral, openai
        env.add_prompt_input("1")  # Primary backend: first one (anthropic)
        env.add_prompt_input("1,2")  # Fallback order for remaining 2

        env.setup_mocks()

        # Execute with ROUTING focus
        init_cmd(focus=InitFocus.ROUTING)

        # Verify routing was configured
        env.verify_routing("custom_routing", expected_default="anthropic")

    def test_configure_routing_with_single_backend(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 4.2: Configure routing with single backend."""
        # Setup environment with existing config and single backend enabled
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_with_configs(include_backends=True, include_routing=True, include_telemetry=True)

        # Enable only openai (disable everything else)
        backends_path = env.inference_dir / "backends.toml"
        toml_doc = load_toml_with_tomlkit(str(backends_path))
        for backend_key in toml_doc:
            if backend_key == "internal":
                continue
            toml_doc[backend_key]["enabled"] = backend_key == "openai"  # type: ignore[index]
        save_toml_to_path(toml_doc, path=str(backends_path))

        # User inputs
        env.add_confirm_input(True)  # Confirm "Would you like to reconfigure routing?"
        env.add_confirm_input(True)  # Confirm "Continue with initialization?"
        env.add_confirm_input(True)  # Confirm creating profile if needed

        env.setup_mocks()

        # Execute with ROUTING focus
        init_cmd(focus=InitFocus.ROUTING)

        # Verify routing is set to all_openai
        env.verify_routing("all_openai")

    def test_telemetry_only_initialization(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 5.1: Initialize telemetry only - just copies template."""
        # Setup environment with existing config but no telemetry
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_with_configs(include_backends=True, include_routing=True, include_telemetry=False)

        # Only need to confirm initialization
        env.add_confirm_input(True)  # Confirm initialization

        env.setup_mocks()

        # Execute with TELEMETRY focus
        init_cmd(focus=InitFocus.TELEMETRY)

        # Verify telemetry was created with default mode (off)
        env.verify_telemetry("off")

    def test_reconfigure_telemetry(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 5.2: Telemetry already configured - reset replaces with template."""
        # Setup environment with existing telemetry
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_with_configs(include_backends=True, include_routing=True, include_telemetry=True)

        # Set initial telemetry to IDENTIFIED
        telemetry_path = env.pipelex_dir / "telemetry.toml"
        toml_doc = load_toml_with_tomlkit(str(telemetry_path))
        toml_doc["custom_posthog"]["mode"] = "identified"  # type: ignore[index]
        save_toml_to_path(toml_doc, path=str(telemetry_path))

        # User inputs - confirm reconfigure
        env.add_confirm_input(True)  # Confirm reconfigure

        env.setup_mocks()

        # Execute with TELEMETRY focus (will prompt to reconfigure since file exists)
        init_cmd(focus=InitFocus.TELEMETRY)

        # After reconfigure, telemetry should be reset to default (off)
        env.verify_telemetry("off")

    def test_reset_routing_with_pipelex_gateway(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case: Reset routing when only pipelex_gateway is enabled (bug fix test)."""
        # Setup environment with existing config and pipelex_gateway enabled
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_with_configs(include_backends=True, include_routing=True, include_telemetry=True)

        # Enable only pipelex_gateway (disable everything else)
        backends_path = env.inference_dir / "backends.toml"
        toml_doc = load_toml_with_tomlkit(str(backends_path))
        for backend_key in toml_doc:
            if backend_key == "internal":
                continue
            toml_doc[backend_key]["enabled"] = backend_key == PipelexBackend.GATEWAY  # type: ignore[index]
        save_toml_to_path(toml_doc, path=str(backends_path))

        # Modify routing to have wrong config (simulating the bug scenario)
        routing_path = env.inference_dir / "routing_profiles.toml"
        routing_doc = load_toml_with_tomlkit(str(routing_path))
        routing_doc["active"] = "wrong_profile"  # type: ignore[index]
        save_toml_to_path(routing_doc, path=str(routing_path))

        # User inputs - need to confirm reset initialization
        env.add_confirm_input(True)  # Confirm "Continue with initialization?" (reset mode)

        env.setup_mocks()

        # Execute with ROUTING focus and reset flag
        init_cmd(focus=InitFocus.ROUTING)

        # Verify routing was reset to all_pipelex_gateway (correct for pipelex_gateway)
        env.verify_routing(PipelexRoutingProfile.ALL_PIPELEX_GATEWAY)

    def test_everything_already_configured(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 7.1: Everything configured - decline reconfigure."""
        # Setup complete environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_with_configs(include_backends=True, include_routing=True, include_telemetry=True)

        # User inputs: decline reconfigure - no prompts needed if everything is configured
        # The command should detect everything is configured and exit

        env.setup_mocks()

        # Execute - should complete immediately since everything is configured
        init_cmd(focus=InitFocus.ALL)

        # Should complete without errors (no changes made)
        # Verify files still exist
        env.verify_file_exists("telemetry.toml")
