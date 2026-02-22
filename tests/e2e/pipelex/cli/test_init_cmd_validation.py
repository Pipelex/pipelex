from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pipelex.cli.commands.init.command import init_cmd
from pipelex.cli.commands.init.ui.types import InitFocus
from pipelex.cogt.model_backends.backend import PipelexBackend
from pipelex.kit.paths import get_kit_configs_dir
from tests.helpers.init_cmd_helpers import MockedInitEnvironment, get_backend_indices_helper

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestInputValidation:
    def test_invalid_backend_index_then_valid(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 8.1: Invalid backend index, then valid."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # User inputs: invalid index, then valid
        env.add_confirm_input(True)  # Confirm initialization
        env.add_confirm_input(True)  # Accept gateway terms of service
        env.add_prompt_input("99")  # Invalid index
        env.add_prompt_input("1")  # Valid: pipelex_gateway

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL)

        # Verify successful completion with valid selection
        env.verify_backends_enabled([PipelexBackend.GATEWAY])

    def test_invalid_non_numeric_input_then_valid(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 8.2: Non-numeric input, then valid."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # User inputs
        env.add_confirm_input(True)  # Confirm initialization
        env.add_confirm_input(True)  # Accept gateway terms of service
        env.add_prompt_input("abc")  # Invalid non-numeric
        env.add_prompt_input("1")  # Valid: pipelex_gateway

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL)

        # Verify successful completion
        env.verify_backends_enabled([PipelexBackend.GATEWAY])

    def test_space_separated_backend_indices(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 8.3: Space-separated backend indices."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # Get indices for openai, anthropic, mistral
        kit_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        indices = get_backend_indices_helper(str(kit_backends), ["openai", "anthropic", "mistral"])
        indices_str = " ".join(str(i) for i in indices)  # Space-separated

        # User inputs
        env.add_confirm_input(True)  # Confirm initialization
        env.add_prompt_input(indices_str)  # Space-separated indices
        env.add_prompt_input("1")  # Primary backend
        env.add_prompt_input("")  # Accept default fallback order

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL)

        # Verify all backends are enabled
        env.verify_backends_enabled(["openai", "anthropic", "mistral"])

    def test_default_selection_press_enter(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 8.4: Default selection (press Enter)."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # User inputs: empty string for default
        env.add_confirm_input(True)  # Confirm initialization
        env.add_confirm_input(True)  # Accept gateway terms of service
        env.add_prompt_input("")  # Empty = default (pipelex_gateway)

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL)

        # Verify default backend is selected
        env.verify_backends_enabled([PipelexBackend.GATEWAY])

    def test_invalid_fallback_order_wrong_count(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 8.7: Invalid fallback order - wrong count."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # Get indices for 3 backends
        kit_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        indices = get_backend_indices_helper(str(kit_backends), ["openai", "anthropic", "mistral"])
        indices_str = ",".join(str(i) for i in indices)

        # User inputs
        env.add_confirm_input(True)  # Confirm initialization
        env.add_prompt_input(indices_str)  # Select 3 backends
        env.add_prompt_input("1")  # Primary backend
        env.add_prompt_input("1")  # Invalid: only 1 index instead of 2
        env.add_prompt_input("1,2")  # Valid: 2 indices for remaining backends

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL)

        # Verify successful completion
        env.verify_backends_enabled(["openai", "anthropic", "mistral"])

    def test_invalid_fallback_order_duplicates(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test Case 8.8: Invalid fallback order - duplicates."""
        # Setup environment
        env = MockedInitEnvironment(tmp_path, mocker)
        env.setup_empty_dir()

        # Get indices for 3 backends
        kit_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        indices = get_backend_indices_helper(str(kit_backends), ["openai", "anthropic", "mistral"])
        indices_str = ",".join(str(i) for i in indices)

        # User inputs
        env.add_confirm_input(True)  # Confirm initialization
        env.add_prompt_input(indices_str)  # Select 3 backends
        env.add_prompt_input("1")  # Primary backend
        env.add_prompt_input("1,1")  # Invalid: duplicate indices
        env.add_prompt_input("1,2")  # Valid: unique indices

        env.setup_mocks()

        # Execute
        init_cmd(focus=InitFocus.ALL)

        # Verify successful completion
        env.verify_backends_enabled(["openai", "anthropic", "mistral"])
