from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cli.commands.init.command import init_cmd
from pipelex.cli.commands.init.ui.types import InitFocus
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit, save_toml_to_path
from tests.helpers.init_cmd_helpers import MockedInitEnvironment, get_backend_indices_helper


class TestFocusedInitialization:
    def test_config_only_initialization(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 2.1: Initialize config files only."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # User inputs
        env.add_confirm_input(True)  # Confirm initialization
        env.add_prompt_input("1")  # Backend selection
        env.add_prompt_input("1")  # Telemetry

        env.setup_mocks()

        # Execute with CONFIG focus
        init_cmd(focus=InitFocus.CONFIG, reset=False)

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
        init_cmd(focus=InitFocus.INFERENCE, reset=False)

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

        # Set pipelex_inference as initially enabled
        backends_path = env.inference_dir / "backends.toml"
        toml_doc = load_toml_with_tomlkit(str(backends_path))
        toml_doc["pipelex_inference"]["enabled"] = True  # type: ignore[index]
        save_toml_to_path(toml_doc, str(backends_path))

        # Get index for mistral
        kit_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        indices = get_backend_indices_helper(str(kit_backends), ["mistral"])

        # User inputs
        env.add_confirm_input(True)  # Confirm reconfigure
        env.add_prompt_input(str(indices[0]))  # Change to mistral
        env.add_confirm_input(True)  # Confirm creating profile if needed

        env.setup_mocks()

        # Execute with INFERENCE focus
        init_cmd(focus=InitFocus.INFERENCE, reset=False)

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
        # Disable pipelex_inference so we get custom_routing instead of pipelex_first
        backends_path = env.inference_dir / "backends.toml"
        toml_doc = load_toml_with_tomlkit(str(backends_path))
        toml_doc["pipelex_inference"]["enabled"] = False  # type: ignore[index]
        toml_doc["anthropic"]["enabled"] = True  # type: ignore[index]
        toml_doc["mistral"]["enabled"] = True  # type: ignore[index]
        toml_doc["openai"]["enabled"] = True  # type: ignore[index]
        save_toml_to_path(toml_doc, str(backends_path))

        # User inputs for routing - need to confirm reconfigure since routing already exists
        env.add_confirm_input(True)  # Confirm reconfigure
        # The backends are enabled and will be listed as: anthropic, mistral, openai
        env.add_prompt_input("1")  # Primary backend: first one (anthropic)
        env.add_prompt_input("1,2")  # Fallback order for remaining 2

        env.setup_mocks()

        # Execute with ROUTING focus
        init_cmd(focus=InitFocus.ROUTING, reset=False)

        # Verify routing was configured
        env.verify_routing("custom_routing", expected_default="anthropic")

    def test_configure_routing_with_single_backend(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 4.2: Configure routing with single backend."""
        # Setup environment with existing config and single backend enabled
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_with_configs(include_backends=True, include_routing=True, include_telemetry=True)

        # Enable only openai
        backends_path = env.inference_dir / "backends.toml"
        toml_doc = load_toml_with_tomlkit(str(backends_path))
        toml_doc["openai"]["enabled"] = True  # type: ignore[index]
        toml_doc["pipelex_inference"]["enabled"] = False  # type: ignore[index]
        save_toml_to_path(toml_doc, str(backends_path))

        # User inputs
        env.add_confirm_input(True)  # Confirm creating profile if needed

        env.setup_mocks()

        # Execute with ROUTING focus
        init_cmd(focus=InitFocus.ROUTING, reset=False)

        # Verify routing is set to all_openai
        env.verify_routing("all_openai")

    def test_telemetry_only_initialization(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 5.1: Initialize telemetry only."""
        # Setup environment with existing config but no telemetry
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_with_configs(include_backends=True, include_routing=True, include_telemetry=False)

        # User inputs
        env.add_confirm_input(True)  # Confirm initialization
        env.add_prompt_input("2")  # Telemetry: ANONYMOUS

        env.setup_mocks()

        # Execute with TELEMETRY focus
        init_cmd(focus=InitFocus.TELEMETRY, reset=False)

        # Verify telemetry was created
        env.verify_telemetry("anonymous")

    def test_reconfigure_telemetry(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 5.2: Telemetry already configured - reconfigure."""
        # Setup environment with existing telemetry
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_with_configs(include_backends=True, include_routing=True, include_telemetry=True)

        # Set initial telemetry to OFF
        telemetry_path = env.pipelex_dir / "telemetry.toml"
        toml_doc = load_toml_with_tomlkit(str(telemetry_path))
        toml_doc["telemetry_mode"] = "off"
        save_toml_to_path(toml_doc, str(telemetry_path))

        # User inputs
        env.add_confirm_input(True)  # Confirm reconfigure
        env.add_prompt_input("3")  # Change to IDENTIFIED

        env.setup_mocks()

        # Execute with TELEMETRY focus
        init_cmd(focus=InitFocus.TELEMETRY, reset=False)

        # Verify telemetry was changed
        env.verify_telemetry("identified")

    def test_reset_routing_with_pipelex_inference(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case: Reset routing when only pipelex_inference is enabled (bug fix test)."""
        # Setup environment with existing config and pipelex_inference enabled
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_with_configs(include_backends=True, include_routing=True, include_telemetry=True)

        # Enable only pipelex_inference
        backends_path = env.inference_dir / "backends.toml"
        toml_doc = load_toml_with_tomlkit(str(backends_path))
        toml_doc["pipelex_inference"]["enabled"] = True  # type: ignore[index]
        toml_doc["openai"]["enabled"] = False  # type: ignore[index]
        toml_doc["anthropic"]["enabled"] = False  # type: ignore[index]
        save_toml_to_path(toml_doc, str(backends_path))

        # Modify routing to have wrong config (simulating the bug scenario)
        routing_path = env.inference_dir / "routing_profiles.toml"
        routing_doc = load_toml_with_tomlkit(str(routing_path))
        routing_doc["active"] = "wrong_profile"  # type: ignore[index]
        save_toml_to_path(routing_doc, str(routing_path))

        # User inputs - need to confirm reset
        env.add_confirm_input(True)  # Confirm reset initialization

        env.setup_mocks()

        # Execute with ROUTING focus and reset flag
        init_cmd(focus=InitFocus.ROUTING, reset=True)

        # Verify routing was reset to pipelex_first (correct for pipelex_inference)
        env.verify_routing("pipelex_first")

    def test_everything_already_configured(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 7.1: Everything configured - decline reconfigure."""
        # Setup complete environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_with_configs(include_backends=True, include_routing=True, include_telemetry=True)

        # User inputs: decline reconfigure - no prompts needed if everything is configured
        # The command should detect everything is configured and exit

        env.setup_mocks()

        # Execute - should complete immediately since everything is configured
        init_cmd(focus=InitFocus.ALL, reset=False)

        # Should complete without errors (no changes made)
        # Verify files still exist
        env.verify_file_exists("telemetry.toml")
