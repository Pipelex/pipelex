"""A home configuration directory, a working directory and a console of each test's own, for the login tests."""

from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from pipelex.cli.commands.login.command import PIPELEX_APP_URL_ENV_KEY
from pipelex.system.environment import PIPELEX_HOME_ENV_KEY
from tests.helpers.pipelex_api_key_env import isolate_pipelex_api_key

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.fixture
def pipelex_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A home configuration directory of the test's own, an empty working directory, and no key in the environment.

    The working directory matters: the runtime loads its `.env` after the home one, so a key set there would be reported.
    """
    home = tmp_path / "pipelex_home"
    working_dir = tmp_path / "work"
    working_dir.mkdir()
    monkeypatch.chdir(working_dir)
    monkeypatch.setenv(PIPELEX_HOME_ENV_KEY, str(home))
    monkeypatch.delenv(PIPELEX_APP_URL_ENV_KEY, raising=False)
    isolate_pipelex_api_key(monkeypatch)
    return home


@pytest.fixture
def output(mocker: MockerFixture) -> StringIO:
    """What `pipelex login` prints."""
    buffer = StringIO()
    mocker.patch("pipelex.cli.commands.login.command.get_console", return_value=Console(file=buffer, width=200))
    return buffer
