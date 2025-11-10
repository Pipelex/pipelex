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


class TestEdgeCases:
    def test_pipelex_inference_sets_pipelex_first(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 9.1: pipelex_inference always sets pipelex_first."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # Get indices for pipelex_inference and openai
        kit_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        indices = get_backend_indices_helper(str(kit_backends), ["pipelex_inference", "openai"])
        indices_str = ",".join(str(i) for i in indices)

        # User inputs - no primary/fallback prompts expected
        env.add_confirm_input(True)  # Confirm initialization
        env.add_prompt_input(indices_str)  # Select pipelex_inference and openai
        env.add_prompt_input("1")  # Telemetry

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL, reset=False)

        # Verify pipelex_first is set automatically
        env.verify_routing("pipelex_first")

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
        env.add_prompt_input("1")  # Telemetry

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL, reset=False)

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
        env.add_prompt_input("1")  # Telemetry

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL, reset=False)

        # Verify custom routing with automatic fallback
        env.verify_routing("custom_routing", expected_default="anthropic", expected_fallback_order=["anthropic", "openai"])

    def test_reset_all_with_flag(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 6.1: Reset all with --reset flag."""
        # Setup environment with existing config
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_with_configs(include_backends=True, include_routing=True, include_telemetry=True)

        # Set initial state
        backends_path = env.inference_dir / "backends.toml"
        toml_doc = load_toml_with_tomlkit(str(backends_path))
        toml_doc["pipelex_inference"]["enabled"] = True  # type: ignore[index]
        save_toml_to_path(toml_doc, str(backends_path))

        telemetry_path = env.pipelex_dir / "telemetry.toml"
        toml_doc_tel = load_toml_with_tomlkit(str(telemetry_path))
        toml_doc_tel["telemetry_mode"] = "identified"
        save_toml_to_path(toml_doc_tel, str(telemetry_path))

        # Get index for anthropic
        kit_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        indices = get_backend_indices_helper(str(kit_backends), ["anthropic"])

        # User inputs
        env.add_confirm_input(True)  # Confirm reset
        env.add_prompt_input(str(indices[0]))  # Select anthropic
        env.add_confirm_input(True)  # Confirm creating profile if needed
        env.add_prompt_input("1")  # Telemetry: OFF

        env.setup_mocks()

        # Execute with reset flag
        init_cmd(focus=InitFocus.ALL, reset=True)

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
        env.add_prompt_input("1")  # Telemetry

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL, reset=False)

        # Verify detailed backends.toml contents
        toml_doc = load_toml_with_tomlkit(str(env.inference_dir / "backends.toml"))

        # Selected backends should be enabled
        assert toml_doc["openai"]["enabled"] is True  # type: ignore[index]
        assert toml_doc["mistral"]["enabled"] is True  # type: ignore[index]

        # Non-selected backends should be disabled
        assert toml_doc["pipelex_inference"]["enabled"] is False  # type: ignore[index]
        assert toml_doc["anthropic"]["enabled"] is False  # type: ignore[index]

        # Internal backend should be enabled
        assert toml_doc["internal"]["enabled"] is True  # type: ignore[index]
