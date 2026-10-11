import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import click
import pytest
import typer
from pytest_mock import MockerFixture

from pipelex.cli._cli import app as pipelex_app
from pipelex.cli.agent_cli._agent_cli import app as agent_app
from pipelex.cli.commands.init.init_usage_stats import note_init_backends, note_init_execution
from pipelex.cli.usage_stats_cli import resolve_invocation, run_with_usage_stats
from pipelex.hosted.run_config import RunExecution
from pipelex.system.runtime import IntegrationMode
from pipelex.system.usage_stats.usage_stats_client import (
    UsageStatsClient,
    configure_usage_stats_for_cli,
    configure_usage_stats_for_runtime,
    note_command_error_domain,
    note_command_hosted,
    show_usage_stats_notice,
)
from pipelex.system.usage_stats.usage_stats_contract import (
    NOTICE_VERSION,
    UsageStatsEnvVar,
    UsageStatsErrorDomain,
    UsageStatsProvider,
    UsageStatsSurface,
    render_notice,
)
from pipelex.system.usage_stats.usage_stats_core import UsageStatsState
from tests.helpers.usage_stats_process import make_project_dir, usage_stats_switched_on
from tests.helpers.usage_stats_schema import assert_envelope_is_valid

_ROOTS: dict[UsageStatsSurface, click.Command] = {
    UsageStatsSurface.PIPELEX: typer.main.get_command(pipelex_app),
    UsageStatsSurface.PIPELEX_AGENT: typer.main.get_command(agent_app),
}


def _root_of(surface: UsageStatsSurface) -> click.Group:
    root = _ROOTS[surface]
    assert isinstance(root, click.Group)
    return root


def _run(*, surface: UsageStatsSurface, args: list[str], invoke: Callable[[], Any]) -> None:
    run_with_usage_stats(root=_root_of(surface), args=args, surface=surface, strip_flags=frozenset({"--no-logo"}), invoke=invoke)


def _debug_events(stderr: str) -> list[dict[str, Any]]:
    return [json.loads(line)["usage_stats_debug"] for line in stderr.splitlines() if line.startswith('{"usage_stats_debug"')]


def _succeed() -> None:
    return None


def _fail_with_input_error() -> None:
    note_command_error_domain(error_domain=UsageStatsErrorDomain.INPUT)
    raise SystemExit(1)


def _interrupted() -> None:
    raise KeyboardInterrupt


def _cancelled_exit() -> None:
    raise SystemExit(130)


def _hosted_run() -> None:
    note_command_hosted()


def _local_init() -> None:
    note_init_backends(backend_keys=["anthropic", "my_company_gateway"])
    note_init_execution(execution=RunExecution.LOCAL)


def _hosted_init() -> None:
    note_init_execution(execution=RunExecution.HOSTED)


def _ask() -> None:
    typer.prompt("Name")


def _confirm() -> None:
    typer.confirm("Proceed?", abort=True)


def _prompting_app() -> click.Command:
    prompting = typer.Typer()
    prompting.command(name="ask")(_ask)
    prompting.command(name="confirm")(_confirm)
    return typer.main.get_command(prompting)


def _off_by_do_not_track(*, state: UsageStatsState, monkeypatch: pytest.MonkeyPatch) -> None:  # ruff: ignore[unused-function-argument]
    monkeypatch.setenv(UsageStatsEnvVar.DO_NOT_TRACK, "1")


def _off_by_tool_switch(*, state: UsageStatsState, monkeypatch: pytest.MonkeyPatch) -> None:  # ruff: ignore[unused-function-argument]
    monkeypatch.setenv(UsageStatsEnvVar.TOOL_SWITCH, "off")


def _off_by_disable(*, state: UsageStatsState, monkeypatch: pytest.MonkeyPatch) -> None:  # ruff: ignore[unused-function-argument]
    state.disable()


def _replaces_its_client_then_is_cancelled() -> None:
    configure_usage_stats_for_runtime(integration_mode=IntegrationMode.PYTEST)
    raise SystemExit(130)


class TestUsageStatsCli:
    @pytest.mark.parametrize(
        ("surface", "args", "command", "is_machine_read"),
        [
            (UsageStatsSurface.PIPELEX, ["validate", "bundle", "x.mthds"], "validate bundle", False),
            (UsageStatsSurface.PIPELEX, ["validate", "--all"], "validate pipe", False),
            (UsageStatsSurface.PIPELEX, ["validate", "my_pipe", "--library-dir", "x"], "validate pipe", False),
            (UsageStatsSurface.PIPELEX, ["codegen", "types", "x.mthds", "--target", "ts-zod"], "codegen types", False),
            (UsageStatsSurface.PIPELEX, ["run", "x.mthds"], "other", False),
            (UsageStatsSurface.PIPELEX, ["no-such-command"], "other", False),
            (UsageStatsSurface.PIPELEX, ["--help"], None, False),
            (UsageStatsSurface.PIPELEX, ["--version"], None, False),
            (UsageStatsSurface.PIPELEX, ["-V"], None, False),
            (UsageStatsSurface.PIPELEX, [], None, False),
            (UsageStatsSurface.PIPELEX, ["show"], None, False),
            (UsageStatsSurface.PIPELEX, ["run", "bundle", "x.mthds", "--help"], None, False),
            (UsageStatsSurface.PIPELEX, ["usage-stats", "status"], None, False),
            (UsageStatsSurface.PIPELEX_AGENT, ["validate", "bundle", "x.mthds"], "validate bundle", False),
            (UsageStatsSurface.PIPELEX_AGENT, ["validate", "bundle", "x.mthds", "--format", "json"], "validate bundle", True),
            (UsageStatsSurface.PIPELEX_AGENT, ["validate", "bundle", "x.mthds", "--format=json"], "validate bundle", True),
            (UsageStatsSurface.PIPELEX_AGENT, ["validate", "bundle", "x.mthds", "--error-format", "json"], "validate bundle", True),
            (
                UsageStatsSurface.PIPELEX_AGENT,
                ["validate", "bundle", "x.mthds", "--format", "json", "--error-format", "markdown"],
                "validate bundle",
                False,
            ),
            (UsageStatsSurface.PIPELEX_AGENT, ["inputs", "pipe", "my_pipe"], "inputs pipe", True),
            (UsageStatsSurface.PIPELEX_AGENT, ["models"], "models", False),
        ],
    )
    def test_invocation_is_resolved_without_reading_arguments(
        self, surface: UsageStatsSurface, args: list[str], command: str | None, is_machine_read: bool
    ) -> None:
        """The command is its path in the tree, never an argument; a JSON error stream is a machine contract."""
        invocation = resolve_invocation(root=_root_of(surface), args=args, surface=surface)
        assert invocation.command == command
        assert invocation.is_machine_read is is_machine_read
        assert invocation.is_statistics_group is (args[:1] == ["usage-stats"])

    def test_notice_once_then_command_completed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        """The notice goes to stderr before the command works, once per machine; the command's event follows."""
        with usage_stats_switched_on(monkeypatch=monkeypatch, home=tmp_path / "home", cwd=make_project_dir(parent=tmp_path), is_debug=True) as state:
            _run(surface=UsageStatsSurface.PIPELEX, args=["--no-logo", "validate", "bundle", "secret_name.mthds"], invoke=_succeed)
            first = capsys.readouterr()
            assert first.out == ""
            assert first.err.splitlines()[0] == render_notice()
            assert state.notice_marker(version=1).exists()
            events = _debug_events(first.err)
            assert len(events) == 1
            assert_envelope_is_valid(events[0])
            assert events[0]["properties"]["command"] == "validate bundle"
            assert events[0]["properties"]["outcome"] == "succeeded"
            assert events[0]["properties"]["notice_version"] == 1
            assert "secret_name" not in first.err
            _run(surface=UsageStatsSurface.PIPELEX, args=["validate", "bundle", "x.mthds"], invoke=_succeed)
            second = capsys.readouterr()
            assert render_notice() not in second.err
            assert len(_debug_events(second.err)) == 1

    def test_machine_read_stderr_gets_no_notice(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        """Under JSON errors the notice is neither printed nor recorded, and the command's statistics are still sent."""
        with usage_stats_switched_on(monkeypatch=monkeypatch, home=tmp_path / "home", cwd=make_project_dir(parent=tmp_path), is_debug=True) as state:
            with pytest.raises(SystemExit):
                _run(
                    surface=UsageStatsSurface.PIPELEX_AGENT, args=["validate", "bundle", "x.mthds", "--format", "json"], invoke=_fail_with_input_error
                )
            captured = capsys.readouterr()
        assert render_notice() not in captured.err
        assert not state.notice_marker(version=1).exists()
        events = _debug_events(captured.err)
        assert len(events) == 1
        assert_envelope_is_valid(events[0])
        assert events[0]["properties"]["surface"] == "pipelex-agent"
        assert events[0]["properties"]["outcome"] == "failed"
        assert events[0]["properties"]["error_domain"] == "input"

    @pytest.mark.parametrize(
        ("invoke", "expected"),
        [
            (_succeed, {"outcome": "succeeded"}),
            (_fail_with_input_error, {"outcome": "failed", "error_domain": "input"}),
            (_interrupted, {"outcome": "cancelled"}),
            (_cancelled_exit, {"outcome": "cancelled"}),
            (_hosted_run, {"outcome": "succeeded", "hosted": True}),
        ],
    )
    def test_outcome_of_the_command(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        invoke: Callable[[], Any],
        expected: dict[str, Any],
    ) -> None:
        with usage_stats_switched_on(monkeypatch=monkeypatch, home=tmp_path / "home", cwd=make_project_dir(parent=tmp_path), is_debug=True):
            try:
                _run(surface=UsageStatsSurface.PIPELEX, args=["run", "bundle", "x.mthds"], invoke=invoke)
            except (SystemExit, KeyboardInterrupt):
                pass
            events = _debug_events(capsys.readouterr().err)
        assert len(events) == 1
        assert_envelope_is_valid(events[0])
        properties = events[0]["properties"]
        for name, value in expected.items():
            assert properties[name] == value
        assert ("error_domain" in properties) is ("error_domain" in expected)
        assert ("hosted" in properties) is ("hosted" in expected)

    @pytest.mark.parametrize(
        ("command", "prompt_answer", "outcome"),
        [
            ("ask", KeyboardInterrupt(), "cancelled"),
            ("confirm", "n", "cancelled"),
            ("ask", EOFError(), "failed"),
        ],
    )
    def test_a_command_stopped_at_a_prompt_is_cancelled(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        mocker: MockerFixture,
        command: str,
        prompt_answer: BaseException | str,
        outcome: str,
    ) -> None:
        """Ctrl-C at a prompt, or a confirmation declined, reaches Typer as Click's `Abort` and exits 1, yet the person stopped it."""
        mocker.patch("click.termui.visible_prompt_func", side_effect=[prompt_answer])
        prompting = _prompting_app()
        with usage_stats_switched_on(monkeypatch=monkeypatch, home=tmp_path / "home", cwd=make_project_dir(parent=tmp_path), is_debug=True):
            with pytest.raises(SystemExit) as exit_info:
                _run(surface=UsageStatsSurface.PIPELEX, args=["run", "bundle", "x.mthds"], invoke=lambda: prompting.main(args=[command]))
            events = _debug_events(capsys.readouterr().err)
        assert exit_info.value.code == 1
        assert len(events) == 1
        assert events[0]["properties"]["outcome"] == outcome

    @pytest.mark.parametrize(
        ("surface", "args", "invoke", "expected"),
        [
            (UsageStatsSurface.PIPELEX, ["init"], _local_init, {"init_execution": "local", "anthropic": True, "custom": True, "openai": False}),
            (UsageStatsSurface.PIPELEX_AGENT, ["init", "--config", "{}"], _hosted_init, {"init_execution": "hosted"}),
            (UsageStatsSurface.PIPELEX, ["init", "routing"], _succeed, {}),
            (UsageStatsSurface.PIPELEX, ["run", "bundle", "x.mthds"], _local_init, {}),
        ],
    )
    def test_init_reports_what_it_set(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        surface: UsageStatsSurface,
        args: list[str],
        invoke: Callable[[], Any],
        expected: dict[str, Any],
    ) -> None:
        """`init` says where it set runs to execute and, once it set backends, a boolean for every provider; no other command carries them."""
        with usage_stats_switched_on(monkeypatch=monkeypatch, home=tmp_path / "home", cwd=make_project_dir(parent=tmp_path), is_debug=True):
            _run(surface=surface, args=args, invoke=invoke)
            events = _debug_events(capsys.readouterr().err)
        assert len(events) == 1
        assert_envelope_is_valid(events[0])
        properties = events[0]["properties"]
        init_properties = {name: value for name, value in properties.items() if name.startswith("init_")}
        assert init_properties.get("init_execution") == expected.get("init_execution")
        backends = {name.removeprefix("init_backend_"): value for name, value in init_properties.items() if name.startswith("init_backend_")}
        expected_backends = {name: value for name, value in expected.items() if name != "init_execution"}
        if expected_backends:
            assert set(backends) == {provider.value for provider in UsageStatsProvider}
            assert {name for name, value in backends.items() if value} == {name for name, value in expected_backends.items() if value}
        else:
            assert backends == {}

    @pytest.mark.parametrize(
        ("args", "is_notice_recorded_before", "switch_off"),
        [
            (["--no-logo", "init"], False, None),
            (["--no-logo", "init"], True, None),
            (["--no-logo", "init", "routing"], True, None),
            (["--no-logo", "init"], False, _off_by_do_not_track),
            (["--no-logo", "init"], True, _off_by_tool_switch),
            (["--no-logo", "init"], True, _off_by_disable),
        ],
    )
    def test_init_carries_the_notice_once(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        mocker: MockerFixture,
        args: list[str],
        is_notice_recorded_before: bool,
        switch_off: Callable[..., None] | None,
    ) -> None:
        """`pipelex init` shows the notice's text on stderr whenever statistics are on, once, the first run's notice standing for it."""
        init_cmd = mocker.patch("pipelex.cli._cli.init_cmd")
        with usage_stats_switched_on(monkeypatch=monkeypatch, home=tmp_path / "home", cwd=make_project_dir(parent=tmp_path), is_debug=True) as state:
            if is_notice_recorded_before:
                state.record_notice(version=NOTICE_VERSION)
            if switch_off is not None:
                switch_off(state=state, monkeypatch=monkeypatch)
            _root_of(UsageStatsSurface.PIPELEX).main(args=args, standalone_mode=False)
            captured = capsys.readouterr()
        init_cmd.assert_called_once()
        assert render_notice() not in captured.out
        assert captured.err.count(render_notice()) == (0 if switch_off else 1)
        assert state.notice_marker(version=NOTICE_VERSION).exists() is (is_notice_recorded_before or switch_off is None)

    def test_the_notice_init_shows_records_nothing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        """Showing the text writes no marker, and a command asked twice shows it once."""
        with usage_stats_switched_on(monkeypatch=monkeypatch, home=tmp_path / "home", cwd=make_project_dir(parent=tmp_path)) as state:
            assert configure_usage_stats_for_cli(surface=UsageStatsSurface.PIPELEX_AGENT, is_machine_read=True) is not None
            show_usage_stats_notice()
            show_usage_stats_notice()
            captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.count(render_notice()) == 1
        assert not state.notice_marker(version=NOTICE_VERSION).exists()

    @pytest.mark.parametrize("args", [["--help"], ["usage-stats", "status"], ["show"]])
    def test_uncounted_invocations_touch_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], args: list[str]
    ) -> None:
        with usage_stats_switched_on(monkeypatch=monkeypatch, home=tmp_path / "home", cwd=make_project_dir(parent=tmp_path), is_debug=True) as state:
            _run(surface=UsageStatsSurface.PIPELEX, args=args, invoke=_succeed)
            captured = capsys.readouterr()
        assert captured.err == ""
        assert not state.state_dir.exists()

    def test_statistics_off_print_and_write_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with usage_stats_switched_on(monkeypatch=monkeypatch, home=tmp_path / "home", cwd=make_project_dir(parent=tmp_path), is_debug=True) as state:
            monkeypatch.setenv(UsageStatsEnvVar.DO_NOT_TRACK, "1")
            _run(surface=UsageStatsSurface.PIPELEX, args=["validate", "bundle", "x.mthds"], invoke=_succeed)
            captured = capsys.readouterr()
        assert captured.err == ""
        assert not state.state_dir.exists()

    def test_statistics_never_replace_the_commands_exit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], mocker: MockerFixture
    ) -> None:
        """A delivery that raises leaves the command's own exit as it was, and the other client of the process still delivers."""
        finish_command = mocker.patch.object(UsageStatsClient, "finish_command", autospec=True, side_effect=[OSError("unlink refused"), None])
        with usage_stats_switched_on(monkeypatch=monkeypatch, home=tmp_path / "home", cwd=make_project_dir(parent=tmp_path), is_debug=True):
            with pytest.raises(SystemExit) as exit_info:
                _run(surface=UsageStatsSurface.PIPELEX, args=["run", "bundle", "x.mthds"], invoke=_replaces_its_client_then_is_cancelled)
            capsys.readouterr()
        assert exit_info.value.code == 130
        assert finish_command.call_count == 2

    def test_a_command_runs_without_statistics_when_they_cannot_be_read(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], mocker: MockerFixture
    ) -> None:
        with usage_stats_switched_on(monkeypatch=monkeypatch, home=tmp_path / "home", cwd=make_project_dir(parent=tmp_path), is_debug=True):
            mocker.patch.object(UsageStatsState, "make_for_current_home", side_effect=RuntimeError("Could not determine home directory."))
            run_with_usage_stats(
                root=_root_of(UsageStatsSurface.PIPELEX),
                args=["validate", "bundle", "x.mthds"],
                surface=UsageStatsSurface.PIPELEX,
                strip_flags=frozenset(),
                invoke=_succeed,
            )
            captured = capsys.readouterr()
        assert captured.err == ""
