"""The key is saved to the home `.env` as `PIPELEX_API_KEY`, readable by its owner only, every other line kept."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from pipelex.cli.commands.init.credentials import set_env_file_entry
from pipelex.cli.commands.login.api_key_store import (
    find_pipelex_api_key,
    find_shadowing_env_file,
    read_saved_pipelex_api_key,
    save_pipelex_api_key,
)
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY
from tests.helpers.login_browser import TEST_KEY


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


class TestApiKeyStore:
    def test_it_saves_to_the_env_of_the_home_named_by_pipelex_home(self, pipelex_home: Path) -> None:
        env_path = save_pipelex_api_key(api_key=TEST_KEY)

        assert env_path == pipelex_home / ".env"
        assert f"{PIPELEX_API_KEY_ENV_KEY}={TEST_KEY}" in env_path.read_text(encoding="utf-8").splitlines()
        assert _mode(env_path) == 0o600
        assert os.environ[PIPELEX_API_KEY_ENV_KEY] == TEST_KEY

    def test_it_keeps_every_other_line_and_tightens_the_mode(self, pipelex_home: Path) -> None:
        pipelex_home.mkdir()
        env_path = pipelex_home / ".env"
        env_path.write_text("# my providers\nOPENAI_API_KEY=sk-openai\n\nexport MISTRAL_API_KEY=mistral\n", encoding="utf-8")
        env_path.chmod(0o644)

        save_pipelex_api_key(api_key=TEST_KEY)

        lines = env_path.read_text(encoding="utf-8").splitlines()
        assert lines[:4] == ["# my providers", "OPENAI_API_KEY=sk-openai", "", "export MISTRAL_API_KEY=mistral"]
        assert lines[4] == f"{PIPELEX_API_KEY_ENV_KEY}={TEST_KEY}"
        assert _mode(env_path) == 0o600

    def test_it_replaces_every_earlier_assignment_of_the_key(self, pipelex_home: Path) -> None:
        """A later duplicate would shadow the new key when the file is loaded, so none is left."""
        pipelex_home.mkdir()
        env_path = pipelex_home / ".env"
        env_path.write_text(
            f"{PIPELEX_API_KEY_ENV_KEY}=plx_sk_old\nOTHER=1\nexport {PIPELEX_API_KEY_ENV_KEY}='plx_sk_older'\n",
            encoding="utf-8",
        )

        save_pipelex_api_key(api_key=TEST_KEY)

        content = env_path.read_text(encoding="utf-8")
        assert "plx_sk_old" not in content
        assert content.count(PIPELEX_API_KEY_ENV_KEY) == 2
        assert read_saved_pipelex_api_key() == TEST_KEY
        assert "OTHER=1" in content.splitlines()

    def test_none_when_neither_the_environment_nor_the_file_holds_one(self, pipelex_home: Path) -> None:
        assert pipelex_home.exists() is False
        assert find_pipelex_api_key() is None

    def test_the_environment_wins(self, pipelex_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        set_env_file_entry(env_path=pipelex_home / ".env", key=PIPELEX_API_KEY_ENV_KEY, value="plx_sk_saved")
        monkeypatch.setenv(PIPELEX_API_KEY_ENV_KEY, "plx_sk_exported")

        assert find_pipelex_api_key() == "plx_sk_exported"

    def test_the_saved_key_is_found_when_the_environment_has_none(self, pipelex_home: Path) -> None:
        set_env_file_entry(env_path=pipelex_home / ".env", key=PIPELEX_API_KEY_ENV_KEY, value="plx_sk_saved")

        assert find_pipelex_api_key() == "plx_sk_saved"

    def test_a_symlinked_env_stays_a_symlink_and_its_target_holds_the_key(self, pipelex_home: Path, tmp_path: Path) -> None:
        """A dotfiles setup links `~/.pipelex/.env` elsewhere: the save writes through the link instead of replacing it."""
        target = tmp_path / "dotfiles" / "pipelex.env"
        target.parent.mkdir()
        target.write_text("OPENAI_API_KEY=sk-openai\n", encoding="utf-8")
        pipelex_home.mkdir()
        link = pipelex_home / ".env"
        link.symlink_to(target)

        save_pipelex_api_key(api_key=TEST_KEY)

        assert link.is_symlink()
        assert link.resolve() == target.resolve()
        assert target.read_text(encoding="utf-8").splitlines() == ["OPENAI_API_KEY=sk-openai", f"{PIPELEX_API_KEY_ENV_KEY}={TEST_KEY}"]

    def test_an_empty_key_in_the_environment_is_no_key_even_with_one_saved(self, pipelex_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """An empty `PIPELEX_API_KEY=` in the working directory's `.env` is what the next process sends, so it is no key."""
        set_env_file_entry(env_path=pipelex_home / ".env", key=PIPELEX_API_KEY_ENV_KEY, value="plx_sk_saved")
        Path(".env").write_text(f"{PIPELEX_API_KEY_ENV_KEY}=\n", encoding="utf-8")
        monkeypatch.setenv(PIPELEX_API_KEY_ENV_KEY, "")

        assert find_pipelex_api_key() is None

    def test_no_working_directory_env_shadows_nothing(self, pipelex_home: Path) -> None:
        set_env_file_entry(env_path=pipelex_home / ".env", key=PIPELEX_API_KEY_ENV_KEY, value="plx_sk_saved")

        assert find_shadowing_env_file() is None

    @pytest.mark.parametrize(
        ("project_line", "saved", "sets_empty_value"),
        [
            (f"{PIPELEX_API_KEY_ENV_KEY}=", "plx_sk_saved", True),
            (f"{PIPELEX_API_KEY_ENV_KEY}=", None, True),
            (f"{PIPELEX_API_KEY_ENV_KEY}=plx_sk_other", "plx_sk_saved", False),
        ],
    )
    def test_a_working_directory_env_setting_another_value_shadows_the_saved_key(
        self, pipelex_home: Path, project_line: str, saved: str | None, sets_empty_value: bool
    ) -> None:
        if saved is not None:
            set_env_file_entry(env_path=pipelex_home / ".env", key=PIPELEX_API_KEY_ENV_KEY, value=saved)
        Path(".env").write_text(f"OTHER=1\n{project_line}\n", encoding="utf-8")

        shadow = find_shadowing_env_file()

        assert shadow is not None
        assert shadow.path == Path(".env").resolve()
        assert shadow.sets_empty_value is sets_empty_value

    @pytest.mark.parametrize(
        ("project_content", "saved"),
        [
            ("OTHER=1\n", "plx_sk_saved"),
            (f"{PIPELEX_API_KEY_ENV_KEY}=plx_sk_saved\n", "plx_sk_saved"),
            (f"{PIPELEX_API_KEY_ENV_KEY}=plx_sk_project_only\n", None),
        ],
    )
    def test_a_working_directory_env_agreeing_with_the_saved_key_shadows_nothing(
        self, pipelex_home: Path, project_content: str, saved: str | None
    ) -> None:
        if saved is not None:
            set_env_file_entry(env_path=pipelex_home / ".env", key=PIPELEX_API_KEY_ENV_KEY, value=saved)
        Path(".env").write_text(project_content, encoding="utf-8")

        assert find_shadowing_env_file() is None

    def test_the_home_env_is_not_its_own_shadow(self, pipelex_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        set_env_file_entry(env_path=pipelex_home / ".env", key=PIPELEX_API_KEY_ENV_KEY, value="")
        monkeypatch.chdir(pipelex_home)

        assert find_shadowing_env_file() is None
