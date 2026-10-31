"""The key is saved to the home `.env` as `PIPELEX_API_KEY`, readable by its owner only, every other line kept, with its base URL when needed."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.cli.commands.init.credentials import set_env_file_entry
from pipelex.cli.commands.login import api_key_store
from pipelex.cli.commands.login.api_key_store import (
    SavedApiKey,
    find_base_url_env_file,
    find_pipelex_api_key,
    find_shadowing_env_file,
    read_saved_pipelex_api_key,
    save_pipelex_api_key,
)
from pipelex.hosted.client_factory import HOSTED_API_DEFAULT_BASE_URL, PIPELEX_API_KEY_ENV_KEY, PIPELEX_BASE_URL_ENV_KEY
from tests.helpers.login_browser import TEST_KEY, saved_base_url

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

DEV_API_URL = "https://api-dev.test"


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


class TestApiKeyStore:
    def test_it_saves_to_the_env_of_the_home_named_by_pipelex_home(self, pipelex_home: Path) -> None:
        saved = save_pipelex_api_key(api_key=TEST_KEY, checked_base_url=HOSTED_API_DEFAULT_BASE_URL)

        env_path = saved.env_path
        assert saved == SavedApiKey(env_path=pipelex_home / ".env")
        assert f"{PIPELEX_API_KEY_ENV_KEY}={TEST_KEY}" in env_path.read_text(encoding="utf-8").splitlines()
        assert _mode(env_path) == 0o600
        assert os.environ[PIPELEX_API_KEY_ENV_KEY] == TEST_KEY

    def test_it_keeps_every_other_line_and_tightens_the_mode(self, pipelex_home: Path) -> None:
        pipelex_home.mkdir()
        env_path = pipelex_home / ".env"
        env_path.write_text("# my providers\nOPENAI_API_KEY=sk-openai\n\nexport MISTRAL_API_KEY=mistral\n", encoding="utf-8")
        env_path.chmod(0o644)

        save_pipelex_api_key(api_key=TEST_KEY, checked_base_url=HOSTED_API_DEFAULT_BASE_URL)

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

        save_pipelex_api_key(api_key=TEST_KEY, checked_base_url=HOSTED_API_DEFAULT_BASE_URL)

        content = env_path.read_text(encoding="utf-8")
        assert "plx_sk_old" not in content
        assert content.count(PIPELEX_API_KEY_ENV_KEY) == 2
        assert read_saved_pipelex_api_key() == TEST_KEY
        assert "OTHER=1" in content.splitlines()

    @pytest.mark.parametrize(
        ("file_content", "checked_base_url", "expected_line"),
        [
            pytest.param("", DEV_API_URL, f"{PIPELEX_BASE_URL_ENV_KEY}={DEV_API_URL}", id="no_base_url_in_the_file"),
            pytest.param(
                f"{PIPELEX_BASE_URL_ENV_KEY}={DEV_API_URL}\n",
                HOSTED_API_DEFAULT_BASE_URL,
                f"{PIPELEX_BASE_URL_ENV_KEY}={HOSTED_API_DEFAULT_BASE_URL}",
                id="the_file_names_another_api",
            ),
            pytest.param(
                f"export {PIPELEX_BASE_URL_ENV_KEY}='https://api-old.test'\n",
                DEV_API_URL,
                f"{PIPELEX_BASE_URL_ENV_KEY}={DEV_API_URL}",
                id="an_exported_quoted_assignment",
            ),
            pytest.param(f"{PIPELEX_BASE_URL_ENV_KEY}=\n", DEV_API_URL, f"{PIPELEX_BASE_URL_ENV_KEY}={DEV_API_URL}", id="an_empty_assignment"),
        ],
    )
    def test_the_base_url_the_key_was_checked_against_is_saved_beside_it_when_the_file_alone_names_another(
        self, pipelex_home: Path, file_content: str, checked_base_url: str, expected_line: str
    ) -> None:
        """A process that does not inherit the login shell's `PIPELEX_BASE_URL` reads the file alone, so it must name the API that checked the key."""
        pipelex_home.mkdir()
        env_path = pipelex_home / ".env"
        env_path.write_text(f"OTHER=1\n{file_content}", encoding="utf-8")

        saved = save_pipelex_api_key(api_key=TEST_KEY, checked_base_url=checked_base_url)

        assert saved == SavedApiKey(env_path=env_path, saved_base_url=checked_base_url)
        lines = env_path.read_text(encoding="utf-8").splitlines()
        assert lines.count(expected_line) == 1
        assert sum(PIPELEX_BASE_URL_ENV_KEY in line for line in lines) == 1
        assert f"{PIPELEX_API_KEY_ENV_KEY}={TEST_KEY}" in lines
        assert lines[0] == "OTHER=1"
        assert saved_base_url(home=pipelex_home) == checked_base_url
        assert os.environ[PIPELEX_BASE_URL_ENV_KEY] == checked_base_url
        assert _mode(env_path) == 0o600

    @pytest.mark.parametrize(
        ("file_content", "checked_base_url"),
        [
            pytest.param("", HOSTED_API_DEFAULT_BASE_URL, id="the_hosted_api_with_no_base_url_in_the_file"),
            pytest.param("", "https://API.pipelex.com:443/", id="the_hosted_api_spelled_otherwise"),
            pytest.param(f"{PIPELEX_BASE_URL_ENV_KEY}={DEV_API_URL}/\n", "https://API-dev.test", id="the_api_the_file_names"),
            pytest.param(f"{PIPELEX_BASE_URL_ENV_KEY}={DEV_API_URL}\n", None, id="no_hosted_client_could_be_built"),
        ],
    )
    def test_no_base_url_is_written_when_the_file_alone_already_names_the_api_that_checked_the_key(
        self, pipelex_home: Path, file_content: str, checked_base_url: str | None
    ) -> None:
        pipelex_home.mkdir()
        env_path = pipelex_home / ".env"
        env_path.write_text(f"OTHER=1\n{file_content}", encoding="utf-8")

        saved = save_pipelex_api_key(api_key=TEST_KEY, checked_base_url=checked_base_url)

        assert saved == SavedApiKey(env_path=env_path)
        assert env_path.read_text(encoding="utf-8").splitlines() == ["OTHER=1", *file_content.splitlines(), f"{PIPELEX_API_KEY_ENV_KEY}={TEST_KEY}"]

    def test_the_key_and_its_base_url_are_written_in_one_write(self, mocker: MockerFixture, pipelex_home: Path) -> None:
        """A reader of the file, the workshop included, never sees the key paired with the API the file named before."""
        write = mocker.spy(api_key_store, "set_env_file_entries")

        save_pipelex_api_key(api_key=TEST_KEY, checked_base_url=DEV_API_URL)

        write.assert_called_once_with(
            env_path=pipelex_home / ".env",
            entries={PIPELEX_API_KEY_ENV_KEY: TEST_KEY, PIPELEX_BASE_URL_ENV_KEY: DEV_API_URL},
        )

    def test_a_base_url_a_env_file_cannot_hold_unquoted_is_left_out_and_reported(self, pipelex_home: Path) -> None:
        unquotable = "https://api dev.test"

        saved = save_pipelex_api_key(api_key=TEST_KEY, checked_base_url=unquotable)

        assert saved == SavedApiKey(env_path=pipelex_home / ".env", unsaved_base_url=unquotable)
        assert (pipelex_home / ".env").read_text(encoding="utf-8").splitlines() == [f"{PIPELEX_API_KEY_ENV_KEY}={TEST_KEY}"]

    @pytest.mark.parametrize(
        ("home_sets_it", "working_dir_sets_it", "expected"),
        [
            pytest.param(False, False, None, id="neither"),
            pytest.param(True, False, "home", id="the_home_env"),
            pytest.param(True, True, "working", id="the_working_directory_env_wins"),
            pytest.param(False, True, "working", id="the_working_directory_env_alone"),
        ],
    )
    def test_the_env_file_giving_the_base_url_is_found(
        self, pipelex_home: Path, home_sets_it: bool, working_dir_sets_it: bool, expected: str | None
    ) -> None:
        set_env_file_entry(env_path=pipelex_home / ".env", key="OTHER", value="1")
        if home_sets_it:
            set_env_file_entry(env_path=pipelex_home / ".env", key=PIPELEX_BASE_URL_ENV_KEY, value=DEV_API_URL)
        Path(".env").write_text(f"{PIPELEX_BASE_URL_ENV_KEY}={DEV_API_URL}\n" if working_dir_sets_it else "OTHER=1\n", encoding="utf-8")

        found = find_base_url_env_file()

        expected_paths = {"home": pipelex_home / ".env", "working": Path(".env").resolve()}
        assert found == (expected_paths[expected] if expected is not None else None)

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

        save_pipelex_api_key(api_key=TEST_KEY, checked_base_url=HOSTED_API_DEFAULT_BASE_URL)

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
