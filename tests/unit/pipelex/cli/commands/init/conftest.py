"""A recorded console and a home configuration directory of each test's own, for the init tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.system.environment import PIPELEX_HOME_ENV_KEY
from tests.helpers.pipelex_api_key_env import isolate_pipelex_api_key
from tests.helpers.recorded_console import RecordedConsole, make_recorded_console

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def recorded_console() -> RecordedConsole:
    """A console whose output the test reads back."""
    return make_recorded_console()


@pytest.fixture
def pipelex_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A home configuration directory of the test's own, an empty working directory, and no key in the environment."""
    home = tmp_path / "pipelex_home"
    working_dir = tmp_path / "work"
    working_dir.mkdir()
    monkeypatch.chdir(working_dir)
    monkeypatch.setenv(PIPELEX_HOME_ENV_KEY, str(home))
    isolate_pipelex_api_key(monkeypatch)
    return home
