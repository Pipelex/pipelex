"""Unit tests for the command-layer control flow of `check_hub_layering_cmd`.

The AST core is exercised from inline snippets in `test_hub_layering_guard.py`; these pin the layer
that turns its findings into a gate. Four things matter and none of them are covered by a snippet
test: the command *exits 1* on any violation (that exit code is what `make check` and CI read),
`quiet` trims only the happy path so a CI failure stays actionable without a re-run, each violation
kind is headed by its own remedy, and a missing scan root fails loudly instead of scanning nothing
and reporting a pass. The filesystem scan is mocked so each branch is driven deterministically
without touching the real `pipelex/` tree.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from pipelex.cli.dev_cli.commands import check_hub_layering_cmd as cmd_mod
from pipelex.cli.dev_cli.commands.check_hub_layering_cmd import check_hub_layering_cmd
from pipelex.cli.dev_cli.commands.hub_layering_guard import (
    RUNTIME_LAYER_PACKAGES,
    HubLayeringViolation,
    HubLayeringViolationKind,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

#: Wide enough that no assertion below depends on where rich decides to wrap.
CONSOLE_WIDTH = 400


def _violation(*, kind: HubLayeringViolationKind, lineno: int = 7) -> HubLayeringViolation:
    return HubLayeringViolation(
        relative_path="pipelex/cogt/sample/worker.py",
        lineno=lineno,
        kind=kind,
        detail="imports `pipelex.interpreter_hub`",
    )


class TestCheckHubLayeringCmd:
    @pytest.fixture
    def console_buffer(self, mocker: MockerFixture) -> io.StringIO:
        """Route every `get_console()` call in the command module to one StringIO-backed console."""
        buffer = io.StringIO()
        mocker.patch.object(cmd_mod, "get_console", return_value=Console(file=buffer, force_terminal=False, width=CONSOLE_WIDTH))
        return buffer

    def test_quiet_success_is_one_line(self, mocker: MockerFixture, console_buffer: io.StringIO) -> None:
        """The Make targets and CI invoke the guard quietly: a clean tree must cost one line."""
        mocker.patch.object(cmd_mod, "collect_all_violations", return_value=[])
        check_hub_layering_cmd(quiet=True)  # returns normally (exit 0)
        output = console_buffer.getvalue()
        assert "Hub-layering check: PASSED" in output
        assert "Runtime layer:" not in output

    def test_verbose_success_names_every_declared_runtime_package(self, mocker: MockerFixture, console_buffer: io.StringIO) -> None:
        """The success panel is where a reader learns what the declaration covers, so it must be complete."""
        mocker.patch.object(cmd_mod, "collect_all_violations", return_value=[])
        check_hub_layering_cmd(quiet=False)
        output = console_buffer.getvalue()
        assert "Hub-layering Check: PASSED" in output
        for package in RUNTIME_LAYER_PACKAGES:
            assert package in output, package

    def test_violations_exit_1_and_locate_every_site(self, mocker: MockerFixture, console_buffer: io.StringIO) -> None:
        """The gate: any violation is a non-zero exit, with every offending line located."""
        violations = [
            _violation(kind=HubLayeringViolationKind.INTERPRETER_HUB_IMPORT, lineno=7),
            _violation(kind=HubLayeringViolationKind.DEAD_HUB_REFERENCE, lineno=42),
        ]
        mocker.patch.object(cmd_mod, "collect_all_violations", return_value=violations)

        with pytest.raises(SystemExit) as exit_info:
            check_hub_layering_cmd(quiet=False)

        assert exit_info.value.code == 1
        output = console_buffer.getvalue()
        assert "Hub-layering Check: FAILED" in output
        assert "pipelex/cogt/sample/worker.py:7" in output
        assert "pipelex/cogt/sample/worker.py:42" in output

    def test_quiet_failure_stays_actionable(self, mocker: MockerFixture, console_buffer: io.StringIO) -> None:
        """Quiet trims success only — a CI failure must carry its sites and remedy, or it needs a re-run."""
        mocker.patch.object(cmd_mod, "collect_all_violations", return_value=[_violation(kind=HubLayeringViolationKind.INTERPRETER_HUB_IMPORT)])

        with pytest.raises(SystemExit) as exit_info:
            check_hub_layering_cmd(quiet=True)

        assert exit_info.value.code == 1
        output = console_buffer.getvalue()
        assert "Hub-layering check: FAILED" in output
        assert "1 violation(s)" in output
        assert "pipelex/cogt/sample/worker.py:7" in output
        assert "take the value as an argument" in output  # the kind's remedy travels with the failure

    def test_violations_are_grouped_by_kind_each_under_its_remedy(self, mocker: MockerFixture, console_buffer: io.StringIO) -> None:
        """Kinds name different remedies, so a mixed run must not present them as one undifferentiated list."""
        violations = [
            _violation(kind=HubLayeringViolationKind.INTERPRETER_HUB_IMPORT, lineno=7),
            _violation(kind=HubLayeringViolationKind.INTERPRETER_HUB_IMPORT, lineno=9),
            _violation(kind=HubLayeringViolationKind.DEAD_HUB_REFERENCE, lineno=42),
        ]
        mocker.patch.object(cmd_mod, "collect_all_violations", return_value=violations)

        with pytest.raises(SystemExit):
            check_hub_layering_cmd(quiet=True)

        output = console_buffer.getvalue()
        assert f"{HubLayeringViolationKind.INTERPRETER_HUB_IMPORT} (2)" in output
        assert f"{HubLayeringViolationKind.DEAD_HUB_REFERENCE} (1)" in output
        assert HubLayeringViolationKind.DEAD_HUB_REFERENCE.remedy in output

    def test_missing_scan_root_fails_without_scanning(self, mocker: MockerFixture, console_buffer: io.StringIO, tmp_path: Path) -> None:
        """A vanished scan root must never read as a pass: scanning nothing finds nothing."""
        mocker.patch.object(cmd_mod, "SCAN_ROOTS", (tmp_path / "ghost_root",))
        scanner = mocker.patch.object(cmd_mod, "collect_all_violations", return_value=[])

        with pytest.raises(SystemExit) as exit_info:
            check_hub_layering_cmd(quiet=True)

        assert exit_info.value.code == 1
        assert "ghost_root" in console_buffer.getvalue()
        scanner.assert_not_called()
