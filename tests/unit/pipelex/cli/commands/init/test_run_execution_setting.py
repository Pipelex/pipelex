"""`[run] execution` is read from and written to a `pipelex.toml`, every other line kept."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cli.commands.init.setup_path import read_run_execution, write_run_execution
from pipelex.cli.exceptions import PipelexCLIError
from pipelex.hosted.run_config import RunExecution
from pipelex.kit.paths import get_kit_configs_dir

if TYPE_CHECKING:
    from pathlib import Path


class TestRunExecutionSetting:
    def test_it_rewrites_the_kit_setting_keeping_the_comments(self, tmp_path: Path) -> None:
        pipelex_toml_path = tmp_path / "pipelex.toml"
        kit_text = (get_kit_configs_dir() / "pipelex.toml").read_text(encoding="utf-8")
        pipelex_toml_path.write_text(kit_text, encoding="utf-8")
        assert read_run_execution(pipelex_toml_path=pipelex_toml_path) == RunExecution.LOCAL

        write_run_execution(pipelex_toml_path=pipelex_toml_path, execution=RunExecution.HOSTED)

        assert read_run_execution(pipelex_toml_path=pipelex_toml_path) == RunExecution.HOSTED
        rewritten = pipelex_toml_path.read_text(encoding="utf-8")
        assert rewritten.replace('execution = "hosted"', 'execution = "local"') == kit_text

    def test_it_creates_the_file_or_the_table_when_missing(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing" / "pipelex.toml"
        write_run_execution(pipelex_toml_path=missing, execution=RunExecution.HOSTED)
        assert read_run_execution(pipelex_toml_path=missing) == RunExecution.HOSTED

        without_run = tmp_path / "without_run.toml"
        without_run.write_text("# mine\n[log]\nlevel = 'info'\n", encoding="utf-8")
        write_run_execution(pipelex_toml_path=without_run, execution=RunExecution.LOCAL)
        assert read_run_execution(pipelex_toml_path=without_run) == RunExecution.LOCAL
        assert without_run.read_text(encoding="utf-8").startswith("# mine\n[log]\nlevel = 'info'\n")

    def test_a_run_that_is_not_a_table_is_refused(self, tmp_path: Path) -> None:
        pipelex_toml_path = tmp_path / "pipelex.toml"
        pipelex_toml_path.write_text('run = "hosted"\n', encoding="utf-8")

        with pytest.raises(PipelexCLIError):
            write_run_execution(pipelex_toml_path=pipelex_toml_path, execution=RunExecution.HOSTED)

    @pytest.mark.parametrize("content", [None, "", "[run]\n", '[run]\nexecution = "elsewhere"\n', "[run\nbroken", 'run = "hosted"\n'])
    def test_reading_finds_none_when_nothing_valid_is_set(self, tmp_path: Path, content: str | None) -> None:
        pipelex_toml_path = tmp_path / "pipelex.toml"
        if content is not None:
            pipelex_toml_path.write_text(content, encoding="utf-8")
        assert read_run_execution(pipelex_toml_path=pipelex_toml_path) is None
