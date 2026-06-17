"""Unit tests for the command-layer control flow of `check_keyword_only_cmd` / `_run_fix`.

These pin the contract of the `--fix` path: it is **non-gating** — it auto-fixes, reports both what was
fixed and what still needs a manual fix, and exits 0 even when unfixable violations remain (the read-only
`check-keyword-only`, run last in `agent-check` and in `make check` / CI, is what enforces compliance).
They also pin that `fix` takes precedence over `report` and that the "nothing to fix" branch trims to one
line only in quiet mode. The filesystem scanning (`fix_all_violations` / `collect_all_violations`) is
mocked so each branch is driven deterministically without touching the real `pipelex/` tree.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from pipelex.cli.dev_cli.commands import check_keyword_only_cmd as cmd_mod
from pipelex.cli.dev_cli.commands.check_keyword_only_cmd import check_keyword_only_cmd
from pipelex.cli.dev_cli.commands.keyword_only_guard import Violation

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


def _violation(name: str) -> Violation:
    return Violation(relative_path="pipelex/sample/module.py", qualified_name=name, lineno=7)


class TestCheckKeywordOnlyCmdFix:
    @pytest.fixture
    def console_buffer(self, mocker: MockerFixture, tmp_path: Path) -> io.StringIO:
        """Route every `get_console()` call to one StringIO-backed console, and point SOURCE_ROOT at a real dir."""
        buffer = io.StringIO()
        mocker.patch.object(cmd_mod, "get_console", return_value=Console(file=buffer, force_terminal=False, width=200))
        # SOURCE_ROOT only needs to exist for the guard's pre-flight check; the scanners are mocked per test.
        mocker.patch.object(cmd_mod, "SOURCE_ROOT", tmp_path)
        return buffer

    def test_fix_only_exits_zero_and_reports_fixed(self, mocker: MockerFixture, console_buffer: io.StringIO) -> None:
        """Fixable-only run: files were rewritten, nothing remains — no SystemExit, the fix is surfaced."""
        mocker.patch.object(cmd_mod, "fix_all_violations", return_value=([_violation("fixed_func")], []))
        check_keyword_only_cmd(fix=True, quiet=True)  # returns normally (exit 0)
        output = console_buffer.getvalue()
        assert "Auto-fixed 1 keyword-only violation(s)" in output
        assert "pipelex/sample/module.py:7" in output
        assert "fixed_func" in output

    def test_unfixable_reports_but_does_not_gate(self, mocker: MockerFixture, console_buffer: io.StringIO) -> None:
        """The fix path is non-gating: an unfixable violation is reported but exits 0 (the read-only check gates)."""
        mocker.patch.object(cmd_mod, "fix_all_violations", return_value=([], [_violation("unfixable_func")]))
        check_keyword_only_cmd(fix=True, quiet=True)  # returns normally (exit 0) — does not raise SystemExit
        output = console_buffer.getvalue()
        assert "1 violation(s) need a manual fix" in output
        assert "unfixable_func" in output
        assert "nothing to fix" not in output  # an unfixable violation is not the empty happy path

    def test_fixed_and_unfixable_reports_both_without_gating(self, mocker: MockerFixture, console_buffer: io.StringIO) -> None:
        """A run that both rewrites files AND leaves unfixable violations reports both — and still exits 0 (non-gating)."""
        mocker.patch.object(
            cmd_mod,
            "fix_all_violations",
            return_value=([_violation("fixed_func")], [_violation("unfixable_func")]),
        )
        check_keyword_only_cmd(fix=True, quiet=True)  # returns normally (exit 0) — the read-only check enforces, not this
        output = console_buffer.getvalue()
        assert "Auto-fixed 1 keyword-only violation(s)" in output  # files were written...
        assert "1 violation(s) need a manual fix" in output  # ...and the rest is reported for a manual fix
        assert "fixed_func" in output
        assert "unfixable_func" in output

    def test_nothing_to_fix_quiet_is_one_line_and_exits_zero(self, mocker: MockerFixture, console_buffer: io.StringIO) -> None:
        """No violations + quiet: the happy path trims to the single 'nothing to fix' line."""
        mocker.patch.object(cmd_mod, "fix_all_violations", return_value=([], []))
        check_keyword_only_cmd(fix=True, quiet=True)  # returns normally (exit 0)
        output = console_buffer.getvalue()
        assert "Keyword-only auto-fix: nothing to fix" in output
        assert "No keyword-only violations." not in output  # the verbose panel is not used in quiet mode

    def test_nothing_to_fix_verbose_prints_success_panel(self, mocker: MockerFixture, console_buffer: io.StringIO) -> None:
        """No violations + verbose: the success panel is shown instead of the one-line message."""
        mocker.patch.object(cmd_mod, "fix_all_violations", return_value=([], []))
        check_keyword_only_cmd(fix=True, quiet=False)  # returns normally (exit 0)
        output = console_buffer.getvalue()
        assert "No keyword-only violations." in output
        assert "nothing to fix" not in output

    def test_fix_takes_precedence_over_report(self, mocker: MockerFixture, console_buffer: io.StringIO) -> None:
        """With both flags set, the fix path runs and the report path (collect_all_violations) is never reached."""
        mocker.patch.object(cmd_mod, "fix_all_violations", return_value=([], []))
        collect_spy = mocker.patch.object(cmd_mod, "collect_all_violations")
        report_spy = mocker.patch.object(cmd_mod, "_print_report")
        check_keyword_only_cmd(report=True, fix=True, quiet=True)
        collect_spy.assert_not_called()
        report_spy.assert_not_called()
        assert "Keyword-only auto-fix: nothing to fix" in console_buffer.getvalue()
