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


class TestEdgeCases:
    def test_pipelex_gateway_sets_all_pipelex_gateway(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 9.1: pipelex_gateway always sets all_pipelex_gateway."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # Get indices for pipelex_gateway and openai
        kit_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        indices = get_backend_indices_helper(str(kit_backends), [PipelexBackend.GATEWAY, "openai"])
        indices_str = ",".join(str(i) for i in indices)

        # User inputs - no primary/fallback prompts expected
        env.add_confirm_input(True)  # Confirm initialization
        env.add_confirm_input(True)  # Accept gateway terms of service
        env.add_prompt_input(indices_str)  # Select pipelex_gateway and openai

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL)

        # Verify all_pipelex_gateway is set automatically
        env.verify_routing(PipelexRoutingProfile.ALL_PIPELEX_GATEWAY)

    def test_single_non_pipelex_backend(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 9.2: Single non-pipelex backend."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # Get index for openai only
        kit_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        indices = get_backend_indices_helper(str(kit_backends), ["openai"])

        # User inputs
        env.add_confirm_input(True)  # Confirm initialization
        env.add_prompt_input(str(indices[0]))  # Select only openai
        env.add_confirm_input(True)  # Confirm creating profile if needed

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL)

        # Verify routing is set to all_openai
        env.verify_routing("all_openai")

    def test_two_backends_automatic_fallback(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 9.5: Two backends (automatic fallback)."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # Get indices for exactly 2 backends (anthropic first, then openai)
        kit_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        indices = get_backend_indices_helper(str(kit_backends), ["anthropic", "openai"])
        indices_str = ",".join(str(i) for i in indices)

        # User inputs - no fallback order prompt for exactly 2 backends
        env.add_confirm_input(True)  # Confirm initialization
        env.add_prompt_input(indices_str)  # Select anthropic, openai
        env.add_prompt_input("1")  # Primary backend: anthropic (first in selection)

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL)

        # Verify custom routing with automatic fallback
        env.verify_routing("custom_routing", expected_default="anthropic", expected_fallback_order=["anthropic", "openai"])

    def test_reset_all_with_flag(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 6.1: Reset all (init always resets)."""
        # Setup environment with existing config
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_with_configs(include_backends=True, include_routing=True, include_telemetry=True)

        # Set initial state
        backends_path = env.inference_dir / "backends.toml"
        toml_doc = load_toml_with_tomlkit(str(backends_path))
        toml_doc[PipelexBackend.GATEWAY]["enabled"] = True  # type: ignore[index]
        save_toml_to_path(toml_doc, path=str(backends_path))

        telemetry_path = env.pipelex_dir / "telemetry.toml"
        toml_doc_tel = load_toml_with_tomlkit(str(telemetry_path))
        toml_doc_tel["custom_posthog"]["mode"] = "identified"  # type: ignore[index]
        save_toml_to_path(toml_doc_tel, path=str(telemetry_path))

        # Get index for anthropic
        kit_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        indices = get_backend_indices_helper(str(kit_backends), ["anthropic"])

        # User inputs
        env.add_confirm_input(True)  # Confirm reset
        env.add_prompt_input(str(indices[0]))  # Select anthropic
        env.add_confirm_input(True)  # Confirm creating profile if needed

        env.setup_mocks()

        # Execute with reset flag
        init_cmd(focus=InitFocus.ALL)

        # Verify configuration was reset
        env.verify_backends_enabled(["anthropic"])
        env.verify_telemetry("off")

    def test_verify_backends_toml_contents(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 10.2: Verify backends.toml contents."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # Get indices for specific backends
        kit_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        indices = get_backend_indices_helper(str(kit_backends), ["openai", "mistral"])
        indices_str = ",".join(str(i) for i in indices)

        # User inputs
        env.add_confirm_input(True)  # Confirm initialization
        env.add_prompt_input(indices_str)  # Select openai, mistral
        env.add_prompt_input("1")  # Primary backend

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL)

        # Verify detailed backends.toml contents
        toml_doc = load_toml_with_tomlkit(str(env.inference_dir / "backends.toml"))

        # Selected backends should be enabled
        assert toml_doc["openai"]["enabled"] is True  # type: ignore[index]
        assert toml_doc["mistral"]["enabled"] is True  # type: ignore[index]

        # Non-selected backends should be disabled
        assert toml_doc[PipelexBackend.GATEWAY]["enabled"] is False  # type: ignore[index]
        assert toml_doc["anthropic"]["enabled"] is False  # type: ignore[index]

        # Internal backend should be enabled
        assert toml_doc["internal"]["enabled"] is True  # type: ignore[index]
