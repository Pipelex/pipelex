import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pipelex.cli.commands.usage_stats_cmd import usage_stats_app
from pipelex.system.usage_stats.usage_stats_contract import TOOL_NAME, UsageStatsEnvVar
from pipelex.system.usage_stats.usage_stats_spool import pending_files, write_spool_file
from pipelex.system.usage_stats.usage_stats_state import is_installation_id
from tests.helpers.usage_stats_process import make_project_dir, usage_stats_switched_on

_STATUS_FIELDS = {"tool", "enabled", "off_by", "installation_id", "notice_version", "internal", "ci", "container", "state_dir"}


class TestUsageStatsCmd:
    def test_status_is_read_only_and_prints_the_status_object(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        with usage_stats_switched_on(monkeypatch=monkeypatch, home=tmp_path / "home", cwd=make_project_dir(parent=tmp_path)) as state:
            state.legacy_config.parent.mkdir(parents=True)
            state.legacy_config.write_text("DISABLE_TELEMETRY=1\n", encoding="utf-8")
            result = CliRunner().invoke(usage_stats_app, ["status", "--format", "json"])
            assert result.exit_code == 0, result.output
            status = json.loads(result.stdout)
            assert set(status) == _STATUS_FIELDS
            assert status["tool"] == "pipelex"
            assert status["enabled"] is False
            assert status["off_by"] == ["legacy_mthds_choice"]
            assert status["installation_id"] is None
            assert status["notice_version"] == 0
            assert status["state_dir"] == str(state.state_dir)
            assert not state.state_dir.exists()
            text = CliRunner().invoke(usage_stats_app, ["status"])
            assert text.exit_code == 0
            assert "legacy_mthds_choice" in text.stdout
            assert not state.state_dir.exists()

    def test_disable_enable_and_reset_id(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """`disable` empties every spool, `enable` names the switches still off, `reset-id` prints a new identifier."""
        with usage_stats_switched_on(monkeypatch=monkeypatch, home=tmp_path / "home", cwd=make_project_dir(parent=tmp_path)) as state:
            first_id = state.obtain_installation_id().value
            write_spool_file(spool_dir=state.spool_dir(tool="mthds"), events=[])
            runner = CliRunner()

            assert runner.invoke(usage_stats_app, ["disable"]).exit_code == 0
            assert state.is_disabled()
            assert pending_files(spool_dir=state.spool_dir(tool="mthds")) == []
            status = json.loads(runner.invoke(usage_stats_app, ["status", "--format", "json"]).stdout)
            assert status["off_by"] == ["machine_choice"]
            assert status["installation_id"] == first_id

            monkeypatch.setenv(UsageStatsEnvVar.DO_NOT_TRACK, "1")
            enabled = runner.invoke(usage_stats_app, ["enable"])
            assert enabled.exit_code == 0
            assert not state.is_disabled()
            assert "do_not_track" in enabled.stdout
            monkeypatch.delenv(UsageStatsEnvVar.DO_NOT_TRACK)
            assert json.loads(runner.invoke(usage_stats_app, ["status", "--format", "json"]).stdout)["enabled"] is True

            write_spool_file(spool_dir=state.spool_dir(tool=TOOL_NAME), events=[])
            reset = runner.invoke(usage_stats_app, ["reset-id"])
            assert reset.exit_code == 0
            new_id = reset.stdout.strip()
            assert is_installation_id(value=new_id)
            assert new_id != first_id
            assert state.read_installation_id() == new_id
            assert pending_files(spool_dir=state.spool_dir(tool=TOOL_NAME)) == []

    def test_disable_reports_a_state_it_cannot_write(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        home = tmp_path / "home"
        home.mkdir()
        (home / ".mthds").write_text("not a directory", encoding="utf-8")
        with usage_stats_switched_on(monkeypatch=monkeypatch, home=home, cwd=make_project_dir(parent=tmp_path)):
            result = CliRunner().invoke(usage_stats_app, ["disable"])
        assert result.exit_code == 1
        assert "could not be turned off" in result.stderr
