"""Tests for credential prompting and persistent storage."""

from __future__ import annotations

import os
import stat
from typing import TYPE_CHECKING

from pipelex.cli.commands.init.credentials import (
    get_required_vars_for_enabled_backends,
    prompt_credentials,
    read_env_file,
    write_env_file,
)

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture


class TestInitCredentials:
    def test_read_env_file_returns_empty_for_nonexistent(self, tmp_path: Path) -> None:
        """Reading a nonexistent file returns an empty dict."""
        result = read_env_file(tmp_path / ".env")
        assert result == {}

    def test_read_env_file_parses_key_value_pairs(self, tmp_path: Path) -> None:
        """Valid key=value lines are parsed correctly."""
        env_path = tmp_path / ".env"
        env_path.write_text("FOO=bar\nBAZ=qux\n")
        result = read_env_file(env_path)
        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_read_env_file_skips_comments_and_blanks(self, tmp_path: Path) -> None:
        """Comments and blank lines are ignored."""
        env_path = tmp_path / ".env"
        env_path.write_text("# comment\n\nFOO=bar\n  # indented comment\n\nBAZ=qux\n")
        result = read_env_file(env_path)
        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_read_env_file_skips_lines_without_equals(self, tmp_path: Path) -> None:
        """Lines without '=' are skipped."""
        env_path = tmp_path / ".env"
        env_path.write_text("FOO=bar\nINVALID_LINE\nBAZ=qux\n")
        result = read_env_file(env_path)
        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_read_env_file_handles_value_with_equals(self, tmp_path: Path) -> None:
        """Values containing '=' are preserved."""
        env_path = tmp_path / ".env"
        env_path.write_text("KEY=val=ue\n")
        result = read_env_file(env_path)
        assert result == {"KEY": "val=ue"}

    def test_write_env_file_creates_file_with_header(self, tmp_path: Path) -> None:
        """Write creates the file with a header comment and entries."""
        env_path = tmp_path / ".env"
        write_env_file(env_path, {"FOO": "bar", "BAZ": "qux"})
        content = env_path.read_text()
        assert "# Pipelex credentials" in content
        assert "FOO=bar" in content
        assert "BAZ=qux" in content

    def test_write_env_file_sets_permissions(self, tmp_path: Path) -> None:
        """Written file has 0600 permissions."""
        env_path = tmp_path / ".env"
        write_env_file(env_path, {"KEY": "value"})
        mode = env_path.stat().st_mode & 0o777
        assert mode == stat.S_IRUSR | stat.S_IWUSR

    def test_write_env_file_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Parent directories are created if they don't exist."""
        env_path = tmp_path / "sub" / "dir" / ".env"
        write_env_file(env_path, {"KEY": "value"})
        assert env_path.is_file()

    def test_write_then_read_roundtrip(self, tmp_path: Path) -> None:
        """Data survives a write/read cycle."""
        env_path = tmp_path / ".env"
        entries = {"ALPHA": "one", "BETA": "two"}
        write_env_file(env_path, entries)
        result = read_env_file(env_path)
        assert result == entries

    def test_write_env_file_merges_with_existing(self, tmp_path: Path) -> None:
        """Writing merges: new keys added, existing keys updated."""
        env_path = tmp_path / ".env"
        write_env_file(env_path, {"OLD": "original", "SHARED": "old_val"})
        existing = read_env_file(env_path)
        existing["SHARED"] = "new_val"
        existing["NEW"] = "fresh"
        write_env_file(env_path, existing)
        result = read_env_file(env_path)
        assert result == {"OLD": "original", "SHARED": "new_val", "NEW": "fresh"}

    def testget_required_vars_for_enabled_backends(self, tmp_path: Path) -> None:
        """Extract vars from enabled backends, ignoring disabled ones."""
        backends_toml = tmp_path / "backends.toml"
        backends_toml.write_text(
            '[openai]\nenabled = true\napi_key = "${OPENAI_API_KEY}"\n\n'
            '[anthropic]\nenabled = false\napi_key = "${ANTHROPIC_API_KEY}"\n\n'
            "[internal]\nenabled = true\n"
        )
        result = get_required_vars_for_enabled_backends(str(backends_toml))
        assert "OPENAI_API_KEY" in result
        assert "ANTHROPIC_API_KEY" not in result

    def test_get_required_vars_returns_empty_for_no_file(self, tmp_path: Path) -> None:
        """Returns empty dict when file doesn't exist."""
        result = get_required_vars_for_enabled_backends(str(tmp_path / "nonexistent.toml"))
        assert result == {}

    def test_get_required_vars_maps_to_display_names(self, tmp_path: Path) -> None:
        """Vars are mapped to their backend display names."""
        backends_toml = tmp_path / "backends.toml"
        backends_toml.write_text('[openai]\ndisplay_name = "OpenAI"\nenabled = true\napi_key = "${OPENAI_API_KEY}"\n\n[internal]\nenabled = true\n')
        result = get_required_vars_for_enabled_backends(str(backends_toml))
        assert result["OPENAI_API_KEY"] == ["OpenAI"]

    def test_prompt_credentials_skips_when_all_set(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """No prompts issued when all required vars are already set."""
        backends_toml = tmp_path / "backends.toml"
        backends_toml.write_text('[openai]\nenabled = true\napi_key = "${OPENAI_API_KEY}"\n\n[internal]\nenabled = true\n')
        mocker.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
        mocker.patch(
            "pipelex.cli.commands.init.credentials.config_manager",
            global_config_dir=str(tmp_path),
        )
        mock_prompt = mocker.patch("pipelex.cli.commands.init.credentials.Prompt.ask")
        mock_console: MagicMock = mocker.MagicMock()
        prompt_credentials(mock_console, str(backends_toml))
        # Should print "already set" message, no Prompt.ask calls
        mock_console.print.assert_called()
        mock_prompt.assert_not_called()

    def test_prompt_credentials_writes_entered_values(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Entered values are written to ~/.pipelex/.env and set in os.environ."""
        backends_toml = tmp_path / "backends.toml"
        backends_toml.write_text('[openai]\nenabled = true\napi_key = "${OPENAI_API_KEY}"\n\n[internal]\nenabled = true\n')
        mocker.patch.dict(os.environ, {}, clear=False)
        # Remove the var if set
        os.environ.pop("OPENAI_API_KEY", None)

        mocker.patch(
            "pipelex.cli.commands.init.credentials.config_manager",
            global_config_dir=str(tmp_path),
        )
        mocker.patch(
            "pipelex.cli.commands.init.credentials.Prompt.ask",
            return_value="sk-test-value",
        )
        mock_console: MagicMock = mocker.MagicMock()
        prompt_credentials(mock_console, str(backends_toml))

        # Verify .env was written
        env_path = tmp_path / ".env"
        assert env_path.is_file()
        content = env_path.read_text()
        assert "OPENAI_API_KEY=sk-test-value" in content

        # Verify env var was set in process
        assert os.environ.get("OPENAI_API_KEY") == "sk-test-value"

        # Cleanup
        os.environ.pop("OPENAI_API_KEY", None)

    def test_prompt_credentials_skips_empty_input(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Empty input skips the credential and doesn't write it."""
        backends_toml = tmp_path / "backends.toml"
        backends_toml.write_text('[openai]\nenabled = true\napi_key = "${OPENAI_API_KEY}"\n\n[internal]\nenabled = true\n')
        mocker.patch.dict(os.environ, {}, clear=False)
        os.environ.pop("OPENAI_API_KEY", None)

        mocker.patch(
            "pipelex.cli.commands.init.credentials.config_manager",
            global_config_dir=str(tmp_path),
        )
        mocker.patch(
            "pipelex.cli.commands.init.credentials.Prompt.ask",
            return_value="",
        )
        mock_console: MagicMock = mocker.MagicMock()
        prompt_credentials(mock_console, str(backends_toml))

        # Verify .env was NOT written (no values entered)
        env_path = tmp_path / ".env"
        assert not env_path.is_file()

    def test_prompt_credentials_preserves_existing_env_entries(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Existing entries in .env are preserved when new ones are added."""
        env_path = tmp_path / ".env"
        write_env_file(env_path, {"EXISTING_KEY": "existing_value"})

        backends_toml = tmp_path / "backends.toml"
        backends_toml.write_text('[openai]\nenabled = true\napi_key = "${OPENAI_API_KEY}"\n\n[internal]\nenabled = true\n')
        mocker.patch.dict(os.environ, {}, clear=False)
        os.environ.pop("OPENAI_API_KEY", None)

        mocker.patch(
            "pipelex.cli.commands.init.credentials.config_manager",
            global_config_dir=str(tmp_path),
        )
        mocker.patch(
            "pipelex.cli.commands.init.credentials.Prompt.ask",
            return_value="sk-new",
        )
        mock_console: MagicMock = mocker.MagicMock()
        prompt_credentials(mock_console, str(backends_toml))

        result = read_env_file(env_path)
        assert result["EXISTING_KEY"] == "existing_value"
        assert result["OPENAI_API_KEY"] == "sk-new"

        # Cleanup
        os.environ.pop("OPENAI_API_KEY", None)

    def test_prompt_credentials_no_backends(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """No prompts when no backends are enabled."""
        backends_toml = tmp_path / "backends.toml"
        backends_toml.write_text('[openai]\nenabled = false\napi_key = "${OPENAI_API_KEY}"\n\n[internal]\nenabled = true\n')
        mocker.patch(
            "pipelex.cli.commands.init.credentials.config_manager",
            global_config_dir=str(tmp_path),
        )
        mock_prompt = mocker.patch("pipelex.cli.commands.init.credentials.Prompt.ask")
        mock_console: MagicMock = mocker.MagicMock()
        prompt_credentials(mock_console, str(backends_toml))
        mock_prompt.assert_not_called()
