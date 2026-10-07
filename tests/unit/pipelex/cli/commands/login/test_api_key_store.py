"""The key is saved to the home `.env` as `PIPELEX_API_KEY`, readable by its owner only, every other line kept."""

from __future__ import annotations

import os
import stat
from typing import TYPE_CHECKING

import pytest

from pipelex.cli.commands.init.credentials import set_env_file_entry
from pipelex.cli.commands.login.api_key_store import find_pipelex_api_key, read_saved_pipelex_api_key, save_pipelex_api_key
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY
from pipelex.system.environment import PIPELEX_HOME_ENV_KEY
from tests.helpers.pipelex_api_key_env import isolate_pipelex_api_key

if TYPE_CHECKING:
    from pathlib import Path

TEST_KEY = "plx_sk_test_not_a_secret"


@pytest.fixture
def pipelex_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A home configuration directory of the test's own, and no key in the environment."""
    home = tmp_path / "pipelex_home"
    monkeypatch.setenv(PIPELEX_HOME_ENV_KEY, str(home))
    isolate_pipelex_api_key(monkeypatch)
    return home


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


class TestSavePipelexApiKey:
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


class TestFindPipelexApiKey:
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
