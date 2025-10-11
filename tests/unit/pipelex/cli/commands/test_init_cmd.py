from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


from pipelex.cli.commands.init_cmd import do_init_config
from pipelex.exceptions import PipelexCLIError


class TestInitCmd:
    def test_do_init_config_copies_all_files(self, tmp_path: Path, mocker: MockerFixture) -> None:
        # Setup directories
        template_dir = tmp_path / "config_template"
        template_dir.mkdir()
        (template_dir / "pipelex.toml").write_text("[tool.pipelex]\nversion = '1.0'")

        target_dir = tmp_path / ".pipelex"
        target_dir.mkdir()

        # Mock config manager
        mock_config_manager = mocker.MagicMock()
        mock_config_manager.pipelex_root_dir = str(tmp_path)
        mock_config_manager.pipelex_config_dir = str(target_dir)

        mocker.patch("pipelex.cli.commands.init_cmd.config_manager", mock_config_manager)
        mock_echo = mocker.patch("typer.echo")

        # Execute
        do_init_config(reset=False)

        # Verify
        assert (target_dir / "pipelex.toml").exists()
        mock_echo.assert_any_call(f"✅ Copied 1 files to {target_dir}:")

    def test_do_init_config_skips_existing_files(self, tmp_path: Path, mocker: MockerFixture) -> None:
        # Setup directories with existing file
        template_dir = tmp_path / "config_template"
        template_dir.mkdir()
        (template_dir / "pipelex.toml").write_text("[tool.pipelex]\nversion = '1.0'")
        (template_dir / "new_file.toml").write_text("[new]\nconfig = 'value'")

        target_dir = tmp_path / ".pipelex"
        target_dir.mkdir()
        (target_dir / "pipelex.toml").write_text("[tool.pipelex]\nversion = '0.9'")

        # Mock config manager
        mock_config_manager = mocker.MagicMock()
        mock_config_manager.pipelex_root_dir = str(tmp_path)
        mock_config_manager.pipelex_config_dir = str(target_dir)

        mocker.patch("pipelex.cli.commands.init_cmd.config_manager", mock_config_manager)
        mock_echo = mocker.patch("typer.echo")

        # Execute
        do_init_config(reset=False)

        # Verify existing file was not overwritten
        content = (target_dir / "pipelex.toml").read_text()
        assert "version = '0.9'" in content

        # Verify new file was copied
        assert (target_dir / "new_file.toml").exists()

        # Verify messages
        calls = [call.args[0] for call in mock_echo.call_args_list]
        assert any("✅ Copied 1 files to" in call for call in calls)
        assert any("ℹ️  Skipped 1 existing files" in call for call in calls)

    def test_do_init_config_reset_overwrites_files(self, tmp_path: Path, mocker: MockerFixture) -> None:
        # Setup directories with existing file
        template_dir = tmp_path / "config_template"
        template_dir.mkdir()
        (template_dir / "pipelex.toml").write_text("[tool.pipelex]\nversion = '1.0'")

        target_dir = tmp_path / ".pipelex"
        target_dir.mkdir()
        (target_dir / "pipelex.toml").write_text("[tool.pipelex]\nversion = '0.9'")

        # Mock config manager
        mock_config_manager = mocker.MagicMock()
        mock_config_manager.pipelex_root_dir = str(tmp_path)
        mock_config_manager.pipelex_config_dir = str(target_dir)

        mocker.patch("pipelex.cli.commands.init_cmd.config_manager", mock_config_manager)
        mock_echo = mocker.patch("typer.echo")

        # Execute
        do_init_config(reset=True)

        # Verify file was overwritten
        content = (target_dir / "pipelex.toml").read_text()
        assert "version = '1.0'" in content

        # Verify no skipped files message
        calls = [call.args[0] for call in mock_echo.call_args_list]
        assert any("✅ Copied 1 files to" in call for call in calls)
        assert not any("ℹ️  Skipped" in call for call in calls)

    def test_do_init_config_nested_directory_structure(self, tmp_path: Path, mocker: MockerFixture) -> None:
        # Setup complex nested structure
        template_dir = tmp_path / "config_template"
        template_dir.mkdir()
        (template_dir / "pipelex.toml").write_text("[tool.pipelex]\nversion = '1.0'")

        inference_dir = template_dir / "inference"
        inference_dir.mkdir()
        (inference_dir / "backends.toml").write_text("[backends]\nconfig = 'value'")

        backends_dir = inference_dir / "backends"
        backends_dir.mkdir()
        (backends_dir / "openai.toml").write_text("[openai]\napi_key = 'test'")

        target_dir = tmp_path / ".pipelex"
        target_dir.mkdir()

        # Mock config manager
        mock_config_manager = mocker.MagicMock()
        mock_config_manager.pipelex_root_dir = str(tmp_path)
        mock_config_manager.pipelex_config_dir = str(target_dir)

        mocker.patch("pipelex.cli.commands.init_cmd.config_manager", mock_config_manager)
        mock_echo = mocker.patch("typer.echo")

        # Execute
        do_init_config(reset=False)

        # Verify all files and directories were created
        assert (target_dir / "pipelex.toml").exists()
        assert (target_dir / "inference").is_dir()
        assert (target_dir / "inference" / "backends.toml").exists()
        assert (target_dir / "inference" / "backends").is_dir()
        assert (target_dir / "inference" / "backends" / "openai.toml").exists()

        # Verify correct number of files copied
        calls = [call.args[0] for call in mock_echo.call_args_list]
        assert any("✅ Copied 3 files to" in call for call in calls)

    def test_do_init_config_handles_permission_error(self, tmp_path: Path, mocker: MockerFixture) -> None:
        # Setup directories
        template_dir = tmp_path / "config_template"
        template_dir.mkdir()
        (template_dir / "pipelex.toml").write_text("[tool.pipelex]\nversion = '1.0'")

        target_dir = tmp_path / ".pipelex"
        target_dir.mkdir()

        # Mock config manager
        mock_config_manager = mocker.MagicMock()
        mock_config_manager.pipelex_root_dir = str(tmp_path)
        mock_config_manager.pipelex_config_dir = str(target_dir)

        mocker.patch("pipelex.cli.commands.init_cmd.config_manager", mock_config_manager)
        mocker.patch("shutil.copy2", side_effect=PermissionError("Permission denied"))

        # Execute and verify exception
        with pytest.raises(PipelexCLIError) as exc_info:
            do_init_config(reset=False)

        assert "Failed to initialize configuration" in str(exc_info.value)

    def test_do_init_config_creates_target_directory(self, tmp_path: Path, mocker: MockerFixture) -> None:
        # Setup template directory only
        template_dir = tmp_path / "config_template"
        template_dir.mkdir()
        (template_dir / "pipelex.toml").write_text("[tool.pipelex]\nversion = '1.0'")

        target_dir = tmp_path / ".pipelex"  # Don't create this

        # Mock config manager
        mock_config_manager = mocker.MagicMock()
        mock_config_manager.pipelex_root_dir = str(tmp_path)
        mock_config_manager.pipelex_config_dir = str(target_dir)

        mocker.patch("pipelex.cli.commands.init_cmd.config_manager", mock_config_manager)
        mock_echo = mocker.patch("typer.echo")

        # Execute
        do_init_config(reset=False)

        # Verify directory was created and file was copied
        assert target_dir.exists()
        assert target_dir.is_dir()
        assert (target_dir / "pipelex.toml").exists()

        # Verify success message
        calls = [call.args[0] for call in mock_echo.call_args_list]
        assert any("✅ Copied 1 files to" in call for call in calls)
