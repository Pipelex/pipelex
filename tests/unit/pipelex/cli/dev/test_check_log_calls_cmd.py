from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from pipelex.cli.dev_cli.commands import check_log_calls_cmd as cmd_mod
from pipelex.cli.dev_cli.commands.check_log_calls_cmd import check_log_calls_cmd
from pipelex.cli.dev_cli.commands.log_call_guard import LogCallGuardError, LogCallRule, OffendingCall, RuleBreach

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

#: Wide enough that no assertion below depends on where Rich decides to wrap.
CONSOLE_WIDTH = 400

LISTED_KEY = "pipelex/core/sample_module.py::Loader.load"
LISTED_SIGNATURE = 'warning: f"Loaded {alias}"'
STALE_SIGNATURE = 'info: f"Fetched {address}"'

OFFENDING_CALL = OffendingCall(
    relative_path="pipelex/core/sample_module.py",
    qualified_name="Loader.load",
    lineno=12,
    signature=LISTED_SIGNATURE,
    breaches=(RuleBreach(rule=LogCallRule.F_STRING, detail="the message is an f-string"),),
)


class TestCheckLogCallsCmd:
    @pytest.fixture
    def console_buffer(self, mocker: MockerFixture) -> io.StringIO:
        """Route every `get_console()` call in the command module to one StringIO-backed console."""
        buffer = io.StringIO()
        mocker.patch.object(cmd_mod, "get_console", return_value=Console(file=buffer, force_terminal=False, width=CONSOLE_WIDTH))
        return buffer

    @pytest.mark.parametrize(
        ("quiet", "expected_verdict"),
        [
            (True, "✓ Log-call check: PASSED (1 baselined call(s) left)"),
            (False, "Log-call Check: PASSED"),
        ],
    )
    def test_a_tree_matching_its_baseline_passes(
        self, mocker: MockerFixture, console_buffer: io.StringIO, quiet: bool, expected_verdict: str
    ) -> None:
        """A tree whose every offending call is listed returns normally, which is exit 0, and a quiet run says so in one line."""
        mocker.patch.object(cmd_mod, "collect_offending_calls", return_value=[OFFENDING_CALL])
        mocker.patch.object(cmd_mod, "load_baseline", return_value={LISTED_KEY: [LISTED_SIGNATURE]})
        check_log_calls_cmd(quiet=quiet)
        output = console_buffer.getvalue()
        assert expected_verdict in output
        if quiet:
            assert output.strip().splitlines() == [expected_verdict]

    @pytest.mark.parametrize("quiet", [True, False])
    def test_an_unlisted_call_exits_1_with_its_site_its_rule_and_the_remedy(
        self, mocker: MockerFixture, console_buffer: io.StringIO, quiet: bool
    ) -> None:
        """The gate: a quiet CI run still carries the site, the rule, its detail and the rule's remedy."""
        mocker.patch.object(cmd_mod, "collect_offending_calls", return_value=[OFFENDING_CALL])
        mocker.patch.object(cmd_mod, "load_baseline", return_value={})

        with pytest.raises(SystemExit) as exit_info:
            check_log_calls_cmd(quiet=quiet)

        assert exit_info.value.code == 1
        output = console_buffer.getvalue()
        assert "pipelex/core/sample_module.py:12" in output
        assert "Loader.load" in output
        assert "f-string: the message is an f-string" in output
        assert LogCallRule.F_STRING.remedy in output

    def test_a_stale_signature_exits_1_naming_it_and_how_to_remove_it(self, mocker: MockerFixture, console_buffer: io.StringIO) -> None:
        mocker.patch.object(cmd_mod, "collect_offending_calls", return_value=[OFFENDING_CALL])
        mocker.patch.object(cmd_mod, "load_baseline", return_value={LISTED_KEY: [LISTED_SIGNATURE, STALE_SIGNATURE]})
        write_baseline = mocker.patch.object(cmd_mod, "write_baseline")

        with pytest.raises(SystemExit) as exit_info:
            check_log_calls_cmd(quiet=True)

        assert exit_info.value.code == 1
        output = console_buffer.getvalue()
        assert "1 baseline signature(s) are stale" in output
        assert STALE_SIGNATURE in output
        assert "pipelex-dev check-log-calls --prune" in output
        write_baseline.assert_not_called()

    def test_prune_removes_the_stale_signature_and_then_passes(self, mocker: MockerFixture, console_buffer: io.StringIO) -> None:
        mocker.patch.object(cmd_mod, "collect_offending_calls", return_value=[OFFENDING_CALL])
        mocker.patch.object(cmd_mod, "load_baseline", return_value={LISTED_KEY: [LISTED_SIGNATURE, STALE_SIGNATURE]})
        write_baseline = mocker.patch.object(cmd_mod, "write_baseline")

        check_log_calls_cmd(prune=True, quiet=True)

        assert write_baseline.call_args.kwargs["baseline"] == {LISTED_KEY: [LISTED_SIGNATURE]}
        output = console_buffer.getvalue()
        assert "Removed 1 stale signature(s) from log_call_baseline.toml" in output
        assert "✓ Log-call check: PASSED (1 baselined call(s) left)" in output

    def test_prune_never_lists_an_unlisted_call(self, mocker: MockerFixture, console_buffer: io.StringIO) -> None:
        mocker.patch.object(cmd_mod, "collect_offending_calls", return_value=[OFFENDING_CALL])
        mocker.patch.object(cmd_mod, "load_baseline", return_value={})
        write_baseline = mocker.patch.object(cmd_mod, "write_baseline")

        with pytest.raises(SystemExit) as exit_info:
            check_log_calls_cmd(prune=True, quiet=True)

        assert exit_info.value.code == 1
        write_baseline.assert_not_called()
        assert "1 call(s) break the conventions" in console_buffer.getvalue()

    def test_report_prints_the_baseline_by_package_area_and_gates_nothing(self, mocker: MockerFixture, console_buffer: io.StringIO) -> None:
        mocker.patch.object(cmd_mod, "collect_offending_calls", return_value=[])
        mocker.patch.object(
            cmd_mod,
            "load_baseline",
            return_value={
                LISTED_KEY: [LISTED_SIGNATURE, STALE_SIGNATURE],
                "pipelex/core/other_module.py::<module>": [LISTED_SIGNATURE],
                "api/pipelex_api/routes.py::start": [LISTED_SIGNATURE],
            },
        )
        check_log_calls_cmd(report=True)
        lines = [line.strip() for line in console_buffer.getvalue().splitlines() if line.strip()]
        assert lines[1:4] == ["pipelex/core  3 call(s)", "api/pipelex_api  1 call(s)", "Total baselined calls: 4"]

    def test_a_guard_error_exits_1_even_when_quiet(self, mocker: MockerFixture, console_buffer: io.StringIO) -> None:
        mocker.patch.object(cmd_mod, "collect_offending_calls", return_value=[])
        mocker.patch.object(cmd_mod, "load_baseline", side_effect=LogCallGuardError("The baseline log_call_baseline.toml was not found"))

        with pytest.raises(SystemExit) as exit_info:
            check_log_calls_cmd(quiet=True)

        assert exit_info.value.code == 1
        assert "✗ Log-call check: FAILED - The baseline log_call_baseline.toml was not found" in console_buffer.getvalue()
