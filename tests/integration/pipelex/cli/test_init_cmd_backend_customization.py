from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cli.commands.init.backends import customize_backends_config
from pipelex.cli.commands.init.config_files import init_config
from pipelex.cogt.model_backends.backend import PipelexBackend
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit
from tests.helpers.init_cmd_helpers import get_backend_indices_helper


class TestBackendCustomization:
    def test_customize_backends_config_with_default_selection(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test backend customization with default selection (pipelex_gateway)."""
        # Setup directories with actual backends.toml
        inference_dir = tmp_path / ".pipelex" / "inference"
        inference_dir.mkdir(parents=True)

        # Copy actual backends.toml from kit
        actual_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        test_backends = inference_dir / "backends.toml"
        shutil.copy2(actual_backends, test_backends)

        # Mock config_manager
        mock_config_manager = mocker.MagicMock()
        mock_config_manager.pipelex_config_dir = tmp_path / ".pipelex"
        mock_config_manager.global_config_dir = tmp_path / ".pipelex"
        mocker.patch("pipelex.cli.commands.init.backends.config_manager", mock_config_manager)

        # Mock console provider
        mocker.patch("pipelex.cli.commands.init.backends.get_console", return_value=mocker.MagicMock())

        # Setup input queues - global patching like MockedInitEnvironment
        prompt_inputs = ["1"]  # Select pipelex_gateway
        confirm_inputs = [True]  # Accept gateway terms

        def prompt_side_effect(*args: Any, **_kwargs: Any) -> str:
            if not prompt_inputs:
                question = str(args[0]) if args else "<unknown prompt>"
                msg = f"Unexpected prompt without predefined input: {question}"
                raise AssertionError(msg)
            return prompt_inputs.pop(0)

        def confirm_side_effect(*args: Any, **_kwargs: Any) -> bool:
            if not confirm_inputs:
                question = str(args[0]) if args else "<unknown confirmation>"
                msg = f"Unexpected confirm without predefined input: {question}"
                raise AssertionError(msg)
            return confirm_inputs.pop(0)

        mocker.patch("rich.prompt.Prompt.ask", side_effect=prompt_side_effect)
        mocker.patch("rich.prompt.Confirm.ask", side_effect=confirm_side_effect)

        # Execute
        customize_backends_config()

        # Verify backends.toml was customized
        toml_doc = load_toml_with_tomlkit(str(test_backends))

        # pipelex_gateway should be enabled
        assert "enabled" in toml_doc[PipelexBackend.GATEWAY]  # type: ignore[operator]
        assert toml_doc[PipelexBackend.GATEWAY]["enabled"] is True  # type: ignore[index]

        # Other backends should be disabled
        for backend in ["openai", "anthropic", "mistral", "fal"]:
            if backend in toml_doc and "enabled" in toml_doc[backend]:  # type: ignore[operator]
                assert toml_doc[backend]["enabled"] is False  # type: ignore[index]

        # internal backend should remain enabled
        assert toml_doc["internal"]["enabled"] is True  # type: ignore[index]

    def test_customize_backends_config_with_multiple_selections(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test backend customization with multiple backend selections."""
        # Setup directories
        inference_dir = tmp_path / ".pipelex" / "inference"
        inference_dir.mkdir(parents=True)

        actual_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        test_backends = inference_dir / "backends.toml"
        shutil.copy2(actual_backends, test_backends)

        # Dynamically get indices for the backends we want to test
        backend_names = ["openai", "anthropic", "mistral"]
        indices = get_backend_indices_helper(str(actual_backends), backend_names)
        indices_str = ",".join(str(idx) for idx in indices)

        # Mock config_manager
        mock_config_manager = mocker.MagicMock()
        mock_config_manager.pipelex_config_dir = tmp_path / ".pipelex"
        mocker.patch("pipelex.cli.commands.init.backends.config_manager", mock_config_manager)

        # Mock console provider
        mocker.patch("pipelex.cli.commands.init.backends.get_console", return_value=mocker.MagicMock())

        # Setup input queues - no gateway selected, so no confirm needed
        prompt_inputs = [indices_str]

        def prompt_side_effect(*args: Any, **_kwargs: Any) -> str:
            if not prompt_inputs:
                question = str(args[0]) if args else "<unknown prompt>"
                msg = f"Unexpected prompt without predefined input: {question}"
                raise AssertionError(msg)
            return prompt_inputs.pop(0)

        mocker.patch("rich.prompt.Prompt.ask", side_effect=prompt_side_effect)

        # Execute
        customize_backends_config()

        # Verify customization
        toml_doc = load_toml_with_tomlkit(str(test_backends))

        # Selected backends should be enabled
        assert toml_doc["openai"]["enabled"] is True  # type: ignore[index]
        assert toml_doc["anthropic"]["enabled"] is True  # type: ignore[index]
        assert toml_doc["mistral"]["enabled"] is True  # type: ignore[index]

        # pipelex_gateway should be disabled
        assert toml_doc[PipelexBackend.GATEWAY]["enabled"] is False  # type: ignore[index]

        # fal should be disabled
        assert toml_doc["fal"]["enabled"] is False  # type: ignore[index]

        # internal should remain enabled
        assert toml_doc["internal"]["enabled"] is True  # type: ignore[index]

    def test_customize_backends_config_with_space_separated_input(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test backend customization with space-separated input."""
        inference_dir = tmp_path / ".pipelex" / "inference"
        inference_dir.mkdir(parents=True)

        actual_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        test_backends = inference_dir / "backends.toml"
        shutil.copy2(actual_backends, test_backends)

        # Dynamically get indices for the backends we want to test
        backend_names = [PipelexBackend.GATEWAY, "openai", "fal"]
        indices = get_backend_indices_helper(str(actual_backends), backend_names)
        indices_str = " ".join(str(idx) for idx in indices)

        # Mock config_manager
        mock_config_manager = mocker.MagicMock()
        mock_config_manager.pipelex_config_dir = tmp_path / ".pipelex"
        mock_config_manager.global_config_dir = tmp_path / ".pipelex"
        mocker.patch("pipelex.cli.commands.init.backends.config_manager", mock_config_manager)

        # Mock console provider
        mocker.patch("pipelex.cli.commands.init.backends.get_console", return_value=mocker.MagicMock())

        # Setup input queues - gateway selected, so confirm needed
        prompt_inputs = [indices_str]
        confirm_inputs = [True]  # Accept gateway terms

        def prompt_side_effect(*args: Any, **_kwargs: Any) -> str:
            if not prompt_inputs:
                question = str(args[0]) if args else "<unknown prompt>"
                msg = f"Unexpected prompt without predefined input: {question}"
                raise AssertionError(msg)
            return prompt_inputs.pop(0)

        def confirm_side_effect(*args: Any, **_kwargs: Any) -> bool:
            if not confirm_inputs:
                question = str(args[0]) if args else "<unknown confirmation>"
                msg = f"Unexpected confirm without predefined input: {question}"
                raise AssertionError(msg)
            return confirm_inputs.pop(0)

        mocker.patch("rich.prompt.Prompt.ask", side_effect=prompt_side_effect)
        mocker.patch("rich.prompt.Confirm.ask", side_effect=confirm_side_effect)

        # Execute
        customize_backends_config()

        # Verify customization
        toml_doc = load_toml_with_tomlkit(str(test_backends))

        # Selected backends should be enabled
        assert toml_doc[PipelexBackend.GATEWAY]["enabled"] is True  # type: ignore[index]
        assert toml_doc["openai"]["enabled"] is True  # type: ignore[index]
        assert toml_doc["fal"]["enabled"] is True  # type: ignore[index]

        # Others should be disabled
        assert toml_doc["anthropic"]["enabled"] is False  # type: ignore[index]
        assert toml_doc["mistral"]["enabled"] is False  # type: ignore[index]

    def test_init_config_copies_files_without_customizing(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that init_config copies non-inference files and skips the inference/ directory."""
        # Setup template directories
        kit_configs_dir = tmp_path / "kit" / "configs"
        kit_configs_dir.mkdir(parents=True)
        (kit_configs_dir / "pipelex.toml").write_text("[tool.pipelex]\nversion = '1.0'")

        inference_dir = kit_configs_dir / "inference"
        inference_dir.mkdir()

        actual_backends = Path(str(get_kit_configs_dir())) / "inference" / "backends.toml"
        shutil.copy2(actual_backends, inference_dir / "backends.toml")

        # Setup target directory
        target_dir = tmp_path / ".pipelex"
        target_dir.mkdir()

        # Mock config_manager
        mocker.patch("pipelex.cli.commands.init.config_files.get_kit_configs_dir", return_value=str(kit_configs_dir))
        mock_config_manager = mocker.MagicMock()
        mock_config_manager.pipelex_config_dir = target_dir
        mocker.patch("pipelex.cli.commands.init.config_files.config_manager", mock_config_manager)
        mocker.patch("typer.echo")

        # Execute init_config
        result = init_config(reset=False)

        # Verify non-inference files were copied
        assert result > 0
        assert (target_dir / "pipelex.toml").exists()

        # Verify inference/ directory was NOT copied (managed by the inference init step)
        assert not (target_dir / "inference").exists()

    def test_customize_backends_handles_missing_file_gracefully(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that customize_backends_config handles missing backends.toml gracefully."""
        # Setup directory WITHOUT backends.toml
        config_dir = tmp_path / ".pipelex"
        config_dir.mkdir()

        mock_config_manager = mocker.MagicMock()
        mock_config_manager.pipelex_config_dir = config_dir
        mocker.patch("pipelex.cli.commands.init.backends.config_manager", mock_config_manager)

        mock_console = mocker.MagicMock()
        mocker.patch("pipelex.cli.commands.init.backends.get_console", return_value=mock_console)

        # Execute - should not raise exception
        customize_backends_config()

        # Verify warning was printed
        mock_console.print.assert_called()
