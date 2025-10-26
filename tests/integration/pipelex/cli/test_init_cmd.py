"""Integration tests for init command backend customization."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cli.commands.init_cmd import customize_backends_config, init_config
from pipelex.kit.paths import get_configs_dir
from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit


class TestBackendCustomization:
    """Integration tests for backend customization during initialization."""

    def test_customize_backends_config_with_default_selection(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test backend customization with default selection (pipelex_inference)."""
        # Setup directories with actual backends.toml
        inference_dir = tmp_path / ".pipelex" / "inference"
        inference_dir.mkdir(parents=True)

        # Copy actual backends.toml from kit
        actual_backends = Path(str(get_configs_dir())) / "inference" / "backends.toml"
        test_backends = inference_dir / "backends.toml"
        shutil.copy2(actual_backends, test_backends)

        # Mock config_manager and user input
        mock_config_manager = mocker.MagicMock()
        mock_config_manager.pipelex_config_dir = str(tmp_path / ".pipelex")
        mocker.patch("pipelex.cli.commands.init_cmd.config_manager", mock_config_manager)

        # Mock Console and Prompt to simulate user selecting default [1]
        mocker.patch("pipelex.cli.commands.init_cmd.Console")
        mocker.patch("pipelex.cli.commands.init_ui.Prompt.ask", return_value="1")

        # Execute
        customize_backends_config()

        # Verify backends.toml was customized
        toml_doc = load_toml_with_tomlkit(str(test_backends))

        # pipelex_inference should be enabled
        assert "enabled" in toml_doc["pipelex_inference"]  # type: ignore[operator]
        assert toml_doc["pipelex_inference"]["enabled"] is True  # type: ignore[index]

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

        actual_backends = Path(str(get_configs_dir())) / "inference" / "backends.toml"
        test_backends = inference_dir / "backends.toml"
        shutil.copy2(actual_backends, test_backends)

        # Mock config_manager
        mock_config_manager = mocker.MagicMock()
        mock_config_manager.pipelex_config_dir = str(tmp_path / ".pipelex")
        mocker.patch("pipelex.cli.commands.init_cmd.config_manager", mock_config_manager)

        # Mock user input: select [6,7,8] (openai, anthropic, mistral) in 1-based indexing
        mocker.patch("pipelex.cli.commands.init_cmd.Console")
        mocker.patch("pipelex.cli.commands.init_ui.Prompt.ask", return_value="6,7,8")

        # Execute
        customize_backends_config()

        # Verify customization
        toml_doc = load_toml_with_tomlkit(str(test_backends))

        # Selected backends should be enabled
        assert toml_doc["openai"]["enabled"] is True  # type: ignore[index]
        assert toml_doc["anthropic"]["enabled"] is True  # type: ignore[index]
        assert toml_doc["mistral"]["enabled"] is True  # type: ignore[index]

        # pipelex_inference should be disabled
        assert toml_doc["pipelex_inference"]["enabled"] is False  # type: ignore[index]

        # fal should be disabled
        assert toml_doc["fal"]["enabled"] is False  # type: ignore[index]

        # internal should remain enabled
        assert toml_doc["internal"]["enabled"] is True  # type: ignore[index]

    def test_customize_backends_config_with_space_separated_input(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test backend customization with space-separated input."""
        inference_dir = tmp_path / ".pipelex" / "inference"
        inference_dir.mkdir(parents=True)

        actual_backends = Path(str(get_configs_dir())) / "inference" / "backends.toml"
        test_backends = inference_dir / "backends.toml"
        shutil.copy2(actual_backends, test_backends)

        mock_config_manager = mocker.MagicMock()
        mock_config_manager.pipelex_config_dir = str(tmp_path / ".pipelex")
        mocker.patch("pipelex.cli.commands.init_cmd.config_manager", mock_config_manager)

        # Mock user input with spaces: "1 6 12" in 1-based indexing
        mocker.patch("pipelex.cli.commands.init_cmd.Console")
        mocker.patch("pipelex.cli.commands.init_ui.Prompt.ask", return_value="1 6 12")

        # Execute
        customize_backends_config()

        # Verify customization
        toml_doc = load_toml_with_tomlkit(str(test_backends))

        # Selected backends should be enabled
        assert toml_doc["pipelex_inference"]["enabled"] is True  # type: ignore[index]
        assert toml_doc["openai"]["enabled"] is True  # type: ignore[index]
        assert toml_doc["fal"]["enabled"] is True  # type: ignore[index]

        # Others should be disabled
        assert toml_doc["anthropic"]["enabled"] is False  # type: ignore[index]
        assert toml_doc["mistral"]["enabled"] is False  # type: ignore[index]

    def test_init_config_copies_files_without_customizing(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that init_config copies files but doesn't customize backends (that's init_cmd's job)."""
        # Setup template directories
        kit_configs_dir = tmp_path / "kit" / "configs"
        kit_configs_dir.mkdir(parents=True)
        (kit_configs_dir / "pipelex.toml").write_text("[tool.pipelex]\nversion = '1.0'")

        inference_dir = kit_configs_dir / "inference"
        inference_dir.mkdir()

        actual_backends = Path(str(get_configs_dir())) / "inference" / "backends.toml"
        shutil.copy2(actual_backends, inference_dir / "backends.toml")

        # Setup target directory
        target_dir = tmp_path / ".pipelex"
        target_dir.mkdir()

        # Mock config_manager
        mocker.patch("pipelex.cli.commands.init_cmd.get_configs_dir", return_value=str(kit_configs_dir))
        mock_config_manager = mocker.MagicMock()
        mock_config_manager.pipelex_config_dir = str(target_dir)
        mocker.patch("pipelex.cli.commands.init_cmd.config_manager", mock_config_manager)
        mocker.patch("typer.echo")

        # Execute init_config
        result = init_config(reset=False)

        # Verify files were copied
        assert result > 0
        assert (target_dir / "pipelex.toml").exists()
        assert (target_dir / "inference" / "backends.toml").exists()

        # Verify backend customization was NOT applied (original values preserved)
        toml_doc = load_toml_with_tomlkit(str(target_dir / "inference" / "backends.toml"))

        # Verify original enabled states from template (template has most backends disabled)
        assert toml_doc["pipelex_inference"]["enabled"] is True  # type: ignore[index]
        assert toml_doc["openai"]["enabled"] is False  # type: ignore[index]
        assert toml_doc["anthropic"]["enabled"] is False  # type: ignore[index]
        assert toml_doc["mistral"]["enabled"] is False  # type: ignore[index]
        assert toml_doc["internal"]["enabled"] is True  # type: ignore[index]

    def test_customize_backends_handles_missing_file_gracefully(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that customize_backends_config handles missing backends.toml gracefully."""
        # Setup directory WITHOUT backends.toml
        config_dir = tmp_path / ".pipelex"
        config_dir.mkdir()

        mock_config_manager = mocker.MagicMock()
        mock_config_manager.pipelex_config_dir = str(config_dir)
        mocker.patch("pipelex.cli.commands.init_cmd.config_manager", mock_config_manager)

        mock_console = mocker.patch("pipelex.cli.commands.init_cmd.Console")

        # Execute - should not raise exception
        customize_backends_config()

        # Verify warning was printed
        mock_console.return_value.print.assert_called()
