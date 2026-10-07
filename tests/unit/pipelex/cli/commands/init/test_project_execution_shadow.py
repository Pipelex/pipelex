"""A global choice of where runs execute is overridden in a project whose `.pipelex/pipelex.toml` sets another: init says so."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cli.commands.init.command import InitChoices, execute_initialization, inspect_initialization
from pipelex.cli.commands.init.setup_path import SetupPath, find_project_execution_shadow, read_run_execution, write_run_execution
from pipelex.cli.commands.init.ui.types import InitFocus
from pipelex.hosted.run_config import RunExecution

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

    from tests.helpers.recorded_console import RecordedConsole


@pytest.fixture
def project_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pipelex_home: Path) -> Path:
    """A project (a `.git` marker) whose `.pipelex/pipelex.toml` runs on this machine, as the working directory.

    It depends on `pipelex_home` so that its change of directory comes after that fixture's.
    """
    assert not pipelex_home.exists()
    project_root = tmp_path / "project"
    (project_root / ".git").mkdir(parents=True)
    config_dir = project_root / ".pipelex"
    write_run_execution(pipelex_toml_path=config_dir / "pipelex.toml", execution=RunExecution.LOCAL)
    monkeypatch.chdir(project_root)
    return config_dir


class TestProjectExecutionShadow:
    def test_a_project_setting_another_execution_is_found(self, project_config_dir: Path, pipelex_home: Path) -> None:
        shadow = find_project_execution_shadow(target_config_dir=pipelex_home, execution=RunExecution.HOSTED, project_config_dir=project_config_dir)

        assert shadow is not None
        assert shadow.pipelex_toml_path == project_config_dir / "pipelex.toml"
        assert shadow.execution == RunExecution.LOCAL

    @pytest.mark.usefixtures("pipelex_home")
    def test_the_same_execution_or_the_project_itself_is_no_shadow(self, project_config_dir: Path, pipelex_home: Path) -> None:
        same = find_project_execution_shadow(target_config_dir=pipelex_home, execution=RunExecution.LOCAL, project_config_dir=project_config_dir)
        itself = find_project_execution_shadow(
            target_config_dir=project_config_dir, execution=RunExecution.HOSTED, project_config_dir=project_config_dir
        )
        none = find_project_execution_shadow(target_config_dir=pipelex_home, execution=RunExecution.HOSTED, project_config_dir=None)

        assert same is None
        assert itself is None
        assert none is None

    def test_a_global_hosted_init_names_the_project_that_overrides_it(
        self, mocker: MockerFixture, project_config_dir: Path, pipelex_home: Path, recorded_console: RecordedConsole
    ) -> None:
        mocker.patch("pipelex.cli.commands.init.command.ensure_pipelex_api_key")
        inspection = inspect_initialization(focus=InitFocus.ALL, local=False)
        assert inspection.target_config_dir == pipelex_home

        execute_initialization(
            console=recorded_console.console, inspection=inspection, choices=InitChoices(setup_path=SetupPath.HOSTED, interactive=False)
        )

        assert read_run_execution(pipelex_toml_path=pipelex_home / "pipelex.toml") == RunExecution.HOSTED
        # Rich wraps long lines at spaces; joining the words back reads the message as written
        printed = " ".join(recorded_console.text().split())
        assert str(project_config_dir / "pipelex.toml") in printed
        assert 'execution = "local"' in printed
        assert "--hosted" in printed
