from pathlib import Path

import pytest

from pipelex.system.usage_stats.usage_stats_contract import UsageStatsEnvVar, UsageStatsOffBy
from pipelex.system.usage_stats.usage_stats_core import UsageStatsState, is_loopback_origin
from pipelex.system.usage_stats.usage_stats_environment import declared_host, is_ci, is_debug, release_version, resolve_endpoint, tool_switch_says_off
from pipelex.system.usage_stats.usage_stats_switches import packaged_default_says_off, project_setting_says_off, read_switches, setting_says_off
from tests.helpers.usage_stats_process import make_project_dir
from tests.unit.pipelex.system.usage_stats.test_data import UsageStatsSwitchCases


class TestUsageStatsSwitches:
    @pytest.mark.parametrize(("value", "says_off"), UsageStatsSwitchCases.TOOL_SWITCH_READINGS)
    def test_tool_switch_reading(self, value: str, says_off: bool) -> None:
        """`PIPELEX_USAGE_STATS` is trimmed and lowercased; an unknown value fails closed."""
        assert tool_switch_says_off(env={UsageStatsEnvVar.TOOL_SWITCH: value}) is says_off
        assert not tool_switch_says_off(env={})

    @pytest.mark.parametrize(("value", "is_on"), UsageStatsSwitchCases.FLAG_READINGS)
    def test_flag_reading(self, value: str, is_on: bool) -> None:
        """`DO_NOT_TRACK`, the debug variable and the CI variables are on unless empty, `0` or `false`."""
        assert is_debug(env={UsageStatsEnvVar.DEBUG: value}) is is_on
        assert is_ci(env={"GITHUB_ACTIONS": value}) is is_on
        off_by = read_switches(
            state=UsageStatsState(home=Path("/nonexistent-home")), env={UsageStatsEnvVar.DO_NOT_TRACK: value}, cwd=Path("/"), is_pytest=False
        )
        assert (UsageStatsOffBy.DO_NOT_TRACK in off_by) is is_on

    @pytest.mark.parametrize(("origin", "is_accepted"), UsageStatsSwitchCases.ENDPOINT_OVERRIDES)
    def test_endpoint_override_is_loopback_only(self, origin: str, is_accepted: bool) -> None:
        assert is_loopback_origin(origin=origin) is is_accepted
        assert resolve_endpoint(env={UsageStatsEnvVar.ENDPOINT_OVERRIDE: origin}) == (origin if is_accepted else None)
        assert resolve_endpoint(env={}) == "https://eu.i.posthog.com"

    def test_declared_host_and_release_version(self) -> None:
        assert declared_host(env={}) is None
        assert declared_host(env={UsageStatsEnvVar.HOST: " Cocode "}) == "cocode"
        assert declared_host(env={UsageStatsEnvVar.HOST: "my-own-tool"}) == "other"
        assert release_version(version="0.83.0") == "0.83.0"
        assert release_version(version="0.84.0rc1") == "0.84.0rc1"
        assert release_version(version="0.83.0+g1a2b3c.d20261011") == "0.83.0"
        assert release_version(version="not-a-version") == "0.0.0"

    @pytest.mark.parametrize(("content", "says_off"), UsageStatsSwitchCases.PROJECT_SETTINGS)
    def test_project_setting_fails_closed(self, tmp_path: Path, content: str | bytes, says_off: bool) -> None:
        """Only `false` turns statistics off, and so does a file nobody can read as the setting."""
        project_dir = make_project_dir(parent=tmp_path)
        config_path = project_dir / ".pipelex" / "pipelex.toml"
        config_path.parent.mkdir()
        if isinstance(content, bytes):
            config_path.write_bytes(content)
        else:
            config_path.write_text(content, encoding="utf-8")
        nested_dir = project_dir / "methods" / "nested"
        nested_dir.mkdir(parents=True)
        assert project_setting_says_off(cwd=nested_dir) is says_off
        assert setting_says_off(config_path=config_path) is says_off

    def test_project_setting_needs_a_project(self, tmp_path: Path) -> None:
        """No project around the directory, or no file in it, means no setting; a directory read as the file fails closed."""
        project_dir = make_project_dir(parent=tmp_path)
        assert not project_setting_says_off(cwd=project_dir)
        (project_dir / ".pipelex" / "pipelex.toml").mkdir(parents=True)
        assert project_setting_says_off(cwd=project_dir)

    def test_home_configuration_is_not_a_switch(self, tmp_path: Path) -> None:
        """`~/.pipelex/pipelex.toml` is pipelex's home layer, never read for the setting."""
        home = tmp_path / "home"
        (home / ".pipelex").mkdir(parents=True)
        (home / ".pipelex" / "pipelex.toml").write_text("[usage_stats]\nenabled = false\n", encoding="utf-8")
        project_dir = make_project_dir(parent=tmp_path)
        off_by = read_switches(state=UsageStatsState(home=home), env={}, cwd=project_dir, is_pytest=False)
        assert off_by == []

    def test_packaged_default(self, tmp_path: Path) -> None:
        packaged = tmp_path / "pipelex.toml"
        packaged.write_text("[usage_stats]\nenabled = true\n", encoding="utf-8")
        assert not packaged_default_says_off(packaged_config_path=packaged)
        packaged.write_text("[usage_stats]\nenabled = false\n", encoding="utf-8")
        assert packaged_default_says_off(packaged_config_path=packaged)
        packaged.write_text("[runtime]\n", encoding="utf-8")
        assert packaged_default_says_off(packaged_config_path=packaged)
        assert packaged_default_says_off(packaged_config_path=tmp_path / "missing.toml")

    def test_every_switch_is_listed_in_the_contracts_order(self, tmp_path: Path) -> None:
        """No switch hides another: `status` names every one that says off, in order."""
        home = tmp_path / "home"
        state = UsageStatsState(home=home)
        state.disable()
        state.legacy_config.write_text("DISABLE_TELEMETRY=1\n", encoding="utf-8")
        project_dir = make_project_dir(parent=tmp_path)
        (project_dir / ".pipelex").mkdir()
        (project_dir / ".pipelex" / "pipelex.toml").write_text("[usage_stats]\nenabled = false\n", encoding="utf-8")
        packaged = tmp_path / "packaged.toml"
        packaged.write_text("[usage_stats]\nenabled = false\n", encoding="utf-8")
        env: dict[str, str] = {
            UsageStatsEnvVar.DO_NOT_TRACK: "1",
            UsageStatsEnvVar.TOOL_SWITCH: "off",
            UsageStatsEnvVar.ENDPOINT_OVERRIDE: "https://example.com",
        }
        off_by = read_switches(state=state, env=env, cwd=project_dir, is_pytest=True, packaged_config_path=packaged)
        assert off_by == list(UsageStatsOffBy)
        assert read_switches(state=UsageStatsState(home=tmp_path / "other-home"), env={}, cwd=project_dir, is_pytest=False) == [
            UsageStatsOffBy.PROJECT_SETTING
        ]
