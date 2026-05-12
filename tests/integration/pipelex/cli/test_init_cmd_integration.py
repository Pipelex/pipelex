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


class TestInitCommandIntegration:
    def test_init_with_all_backends_selection(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test initialization with 'all' backends selection."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # User inputs: confirm init, select all backends
        env.add_confirm_input(True)  # Confirm initialization
        env.add_confirm_input(True)  # Accept gateway terms of service (since "all" includes gateway)
        env.add_prompt_input("all")  # Select all backends

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL)

        # Verify all backends are enabled (except internal which is separate)
        toml_doc = load_toml_with_tomlkit(str(env.inference_dir / "backends.toml"))
        for backend_key in toml_doc:
            if backend_key != "internal":
                assert toml_doc[backend_key]["enabled"] is True  # type: ignore[index]

        # Verify routing was set to all_pipelex_gateway (since pipelex_gateway is in "all")
        env.verify_routing(PipelexRoutingProfile.ALL_PIPELEX_GATEWAY)

        # Verify telemetry (always "off" - default from template)
        env.verify_telemetry("off")

    def test_init_with_multiple_backends_custom_routing(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test initialization with multiple backends and custom routing."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # Get indices for anthropic, mistral, openai (they will be selected in this order)
        kit_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        indices = get_backend_indices_helper(str(kit_backends), ["anthropic", "mistral", "openai"])
        indices_str = ",".join(str(i) for i in indices)

        # User inputs
        env.add_confirm_input(True)  # Confirm initialization
        env.add_prompt_input(indices_str)  # Select anthropic, mistral, openai
        env.add_prompt_input("1")  # Primary backend: first one (anthropic)
        env.add_prompt_input("")  # Accept default fallback order

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL)

        # Verify backends
        env.verify_backends_enabled(["openai", "anthropic", "mistral"])

        # Verify custom routing was created
        env.verify_routing("custom_routing", expected_default="anthropic")

        # Verify telemetry (always "off" - default from template)
        env.verify_telemetry("off")

    def test_init_with_single_backend_auto_routing(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test initialization with single backend sets auto routing."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # Get index for openai
        kit_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        indices = get_backend_indices_helper(str(kit_backends), ["openai"])

        # User inputs
        env.add_confirm_input(True)  # Confirm initialization
        env.add_prompt_input(str(indices[0]))  # Select only openai
        env.add_confirm_input(True)  # Confirm creating profile if needed

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL)

        # Verify only openai is enabled
        env.verify_backends_enabled(["openai"])

        # Verify routing is set to all_openai
        env.verify_routing("all_openai")

        # Verify telemetry (always "off" - default from template)
        env.verify_telemetry("off")

    def test_init_config_only_focus(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test focused initialization: config files only."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # User inputs - CONFIG focus still runs full init on first time
        env.add_confirm_input(True)  # Confirm initialization
        env.add_confirm_input(True)  # Accept gateway terms of service
        env.add_prompt_input("1")  # Backend selection (pipelex_gateway)

        env.setup_mocks()

        # Execute with CONFIG focus
        init_cmd(focus=InitFocus.CONFIG)

        # Verify config files exist
        env.verify_file_exists("pipelex.toml")
        env.verify_file_exists("inference/backends.toml")

        # CONFIG focus on first init triggers full flow
        env.verify_backends_enabled([PipelexBackend.GATEWAY])
        env.verify_routing(PipelexRoutingProfile.ALL_PIPELEX_GATEWAY)
        # Telemetry should be created
        if (env.pipelex_dir / "telemetry.toml").exists():
            env.verify_telemetry("off")

    def test_init_inference_only_focus(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test focused initialization: inference only."""
        # Setup environment with existing config
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_with_configs(include_backends=True, include_routing=True, include_telemetry=False)

        # Get indices for anthropic and mistral
        kit_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        indices = get_backend_indices_helper(str(kit_backends), ["anthropic", "mistral"])
        indices_str = ",".join(str(i) for i in indices)

        # User inputs - need to confirm reconfigure since backends already exist
        env.add_confirm_input(True)  # Confirm reconfigure
        env.add_prompt_input(indices_str)  # Select anthropic, mistral
        env.add_prompt_input("1")  # Primary backend: first one (anthropic)
        env.add_prompt_input("")  # Accept default fallback order

        env.setup_mocks()

        # Execute with INFERENCE focus
        init_cmd(focus=InitFocus.INFERENCE)

        # Verify backends
        env.verify_backends_enabled(["anthropic", "mistral"])

        # Verify routing was configured (anthropic is first in selection)
        env.verify_routing("custom_routing", expected_default="anthropic")

        # Verify telemetry was NOT created (inference focus only)
        env.verify_file_not_exists("telemetry.toml")

    def test_init_telemetry_only_focus(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test focused initialization: telemetry only."""
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

    def test_init_telemetry_project_uses_commented_template(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Project-targeted telemetry init must drop the commented-out template so it
        doesn't shadow the user's global telemetry settings.
        """
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_with_configs(include_backends=True, include_routing=True, include_telemetry=False)

        env.add_confirm_input(True)  # Confirm initialization
        env.setup_mocks()

        init_cmd(focus=InitFocus.TELEMETRY, local=True)

        telemetry_path = env.pipelex_dir / "telemetry.toml"
        assert telemetry_path.exists()
        content = telemetry_path.read_text(encoding="utf-8")
        # Every non-blank line in the project template must be a comment — no active
        # assignments are allowed, otherwise the file would shadow global telemetry settings.
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            assert line.startswith("#"), f"Project template should be fully commented; found active line: {raw_line!r}"
        # Still documents available knobs as "invitation to override" markers.
        assert "# [custom_posthog]" in content
        assert "# [langfuse]" in content

    def test_init_with_reset_flag(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test initialization with reset flag overwrites existing config."""
        # Setup environment with existing config
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_with_configs(include_backends=True, include_routing=True, include_telemetry=True)

        # Modify telemetry to a different value (using new nested path)
        telemetry_path = env.pipelex_dir / "telemetry.toml"
        toml_doc = load_toml_with_tomlkit(str(telemetry_path))
        toml_doc["custom_posthog"]["mode"] = "identified"  # type: ignore[index]
        save_toml_to_path(toml_doc, str(telemetry_path))

        # Get index for mistral
        kit_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        indices = get_backend_indices_helper(str(kit_backends), ["mistral"])

        # User inputs
        env.add_confirm_input(True)  # Confirm reset
        env.add_prompt_input(str(indices[0]))  # Select mistral only
        env.add_confirm_input(True)  # Confirm creating profile if needed

        env.setup_mocks()

        # Execute with reset flag
        init_cmd(focus=InitFocus.ALL)

        # Verify backends were reset
        env.verify_backends_enabled(["mistral"])

        # Verify telemetry was reset to OFF (default from template)
        env.verify_telemetry("off")

    def test_init_reconfigure_existing_inference(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test reconfiguring inference when already configured."""
        # Setup environment with existing config
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_with_configs(include_backends=True, include_routing=True, include_telemetry=True)

        # Set pipelex_gateway as enabled initially
        backends_path = env.inference_dir / "backends.toml"
        toml_doc = load_toml_with_tomlkit(str(backends_path))
        toml_doc[PipelexBackend.GATEWAY]["enabled"] = True  # type: ignore[index]
        save_toml_to_path(toml_doc, str(backends_path))

        # Get index for openai
        kit_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        indices = get_backend_indices_helper(str(kit_backends), ["openai"])

        # User inputs
        env.add_confirm_input(True)  # Confirm reconfigure
        env.add_prompt_input(str(indices[0]))  # Change to openai
        env.add_confirm_input(True)  # Confirm creating profile if needed

        env.setup_mocks()

        # Execute with INFERENCE focus
        init_cmd(focus=InitFocus.INFERENCE)

        # Verify backend was changed
        env.verify_backends_enabled(["openai"])

        # Verify routing was updated
        env.verify_routing("all_openai")

    def test_init_two_backends_automatic_fallback(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that two backends automatically set fallback without prompting order."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # Get indices for exactly 2 backends (anthropic first, then openai)
        kit_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        indices = get_backend_indices_helper(str(kit_backends), ["anthropic", "openai"])
        indices_str = ",".join(str(i) for i in indices)

        # User inputs - note: no fallback order prompt for 2 backends
        env.add_confirm_input(True)  # Confirm initialization
        env.add_prompt_input(indices_str)  # Select anthropic, openai
        env.add_prompt_input("1")  # Primary backend: anthropic (first in selection)

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL)

        # Verify backends
        env.verify_backends_enabled(["openai", "anthropic"])

        # Verify custom routing with automatic fallback order
        env.verify_routing("custom_routing", expected_default="anthropic", expected_fallback_order=["anthropic", "openai"])

    def test_init_pipelex_gateway_sets_all_pipelex_gateway(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that selecting pipelex_gateway automatically sets all_pipelex_gateway routing."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # Get indices for pipelex_gateway and openai
        kit_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        indices = get_backend_indices_helper(str(kit_backends), [PipelexBackend.GATEWAY, "openai"])
        indices_str = ",".join(str(i) for i in indices)

        # User inputs - no primary/fallback prompts because pipelex_gateway is included
        env.add_confirm_input(True)  # Confirm initialization
        env.add_confirm_input(True)  # Accept gateway terms of service
        env.add_prompt_input(indices_str)  # Select pipelex_gateway and openai

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL)

        # Verify backends
        env.verify_backends_enabled([PipelexBackend.GATEWAY, "openai"])

        # Verify routing is automatically set to all_pipelex_gateway
        env.verify_routing(PipelexRoutingProfile.ALL_PIPELEX_GATEWAY)
