"""Unit tests for the command-layer control flow of `check_hub_layering_cmd`.

The AST core is exercised from inline snippets in `test_hub_layering_guard.py` and from tmp trees in
`test_hub_layering_transitive.py`; these pin the layer that turns their findings into a gate. Five
things matter and none of them are covered by those: the command *exits 1* on any violation (that exit
code is what `make check` and CI read), `quiet` trims only the happy path so a CI failure stays
actionable without a re-run, each violation kind is headed by its own remedy, both scans are merged
into one report, and a missing scan root fails loudly instead of scanning nothing and reporting a
pass. Both scans are mocked so each branch is driven deterministically without touching the real
`pipelex/` tree.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from pipelex.cli.dev_cli.commands import check_hub_layering_cmd as cmd_mod
from pipelex.cli.dev_cli.commands.check_hub_layering_cmd import check_hub_layering_cmd
from pipelex.cli.dev_cli.commands.hub_layering_guard import (
    KERNEL_LAYER_PACKAGES,
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


def _patch_scans(
    mocker: MockerFixture,
    *,
    per_file: list[HubLayeringViolation] | None = None,
    transitive: list[HubLayeringViolation] | None = None,
) -> None:
    """Drive both of the command's scans. Mocking only one would leave the other walking the real tree."""
    mocker.patch.object(cmd_mod, "collect_all_violations", return_value=per_file or [])
    mocker.patch.object(cmd_mod, "collect_transitive_violations", return_value=transitive or [])


class TestCheckHubLayeringCmd:
    @pytest.fixture
    def console_buffer(self, mocker: MockerFixture) -> io.StringIO:
        """Route every `get_console()` call in the command module to one StringIO-backed console."""
        buffer = io.StringIO()
        mocker.patch.object(cmd_mod, "get_console", return_value=Console(file=buffer, force_terminal=False, width=CONSOLE_WIDTH))
        return buffer

    def test_quiet_success_is_one_line(self, mocker: MockerFixture, console_buffer: io.StringIO) -> None:
        """The Make targets and CI invoke the guard quietly: a clean tree must cost one line."""
        _patch_scans(mocker)
        check_hub_layering_cmd(quiet=True)  # returns normally (exit 0)
        output = console_buffer.getvalue()
        assert "Hub-layering check: PASSED" in output
        assert "Kernel layer:" not in output

    def test_verbose_success_names_every_declared_kernel_package(self, mocker: MockerFixture, console_buffer: io.StringIO) -> None:
        """The success panel is where a reader learns what the declaration covers, so it must be complete."""
        _patch_scans(mocker)
        check_hub_layering_cmd(quiet=False)
        output = console_buffer.getvalue()
        assert "Hub-layering Check: PASSED" in output
        for package in KERNEL_LAYER_PACKAGES:
            assert package in output, package

    def test_violations_exit_1_and_locate_every_site(self, mocker: MockerFixture, console_buffer: io.StringIO) -> None:
        """The gate: any violation is a non-zero exit, with every offending line located."""
        violations = [
            _violation(kind=HubLayeringViolationKind.INTERPRETER_HUB_IMPORT, lineno=7),
            _violation(kind=HubLayeringViolationKind.DEAD_HUB_REFERENCE, lineno=42),
        ]
        _patch_scans(mocker, per_file=violations)

        with pytest.raises(SystemExit) as exit_info:
            check_hub_layering_cmd(quiet=False)

        assert exit_info.value.code == 1
        output = console_buffer.getvalue()
        assert "Hub-layering Check: FAILED" in output
        assert "pipelex/cogt/sample/worker.py:7" in output
        assert "pipelex/cogt/sample/worker.py:42" in output

    def test_quiet_failure_stays_actionable(self, mocker: MockerFixture, console_buffer: io.StringIO) -> None:
        """Quiet trims success only — a CI failure must carry its sites and remedy, or it needs a re-run."""
        _patch_scans(mocker, per_file=[_violation(kind=HubLayeringViolationKind.INTERPRETER_HUB_IMPORT)])

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
        _patch_scans(mocker, per_file=violations)

        with pytest.raises(SystemExit):
            check_hub_layering_cmd(quiet=True)

        output = console_buffer.getvalue()
        assert f"{HubLayeringViolationKind.INTERPRETER_HUB_IMPORT} (2)" in output
        assert f"{HubLayeringViolationKind.DEAD_HUB_REFERENCE} (1)" in output
        assert HubLayeringViolationKind.DEAD_HUB_REFERENCE.remedy in output

    def test_both_scans_are_reported_together_under_one_gate(self, mocker: MockerFixture, console_buffer: io.StringIO) -> None:
        """The per-file rules and the transitive rule are two passes but one gate.

        Both passes' findings land in the same report, counted together and each under its own kind's
        remedy — a run must never present one pass and drop the other.
        """
        transitive = HubLayeringViolation(
            relative_path="pipelex/cogt/aggregator.py",
            lineno=3,
            kind=HubLayeringViolationKind.INTERPRETER_HUB_TRANSITIVE,
            detail="reaches `pipelex.interpreter_hub` via pipelex.runtime_bridge.orchestrator → pipelex.interpreter_hub",
        )
        _patch_scans(mocker, per_file=[_violation(kind=HubLayeringViolationKind.DEAD_HUB_REFERENCE, lineno=42)], transitive=[transitive])

        with pytest.raises(SystemExit) as exit_info:
            check_hub_layering_cmd(quiet=True)

        assert exit_info.value.code == 1
        output = console_buffer.getvalue()
        assert "2 violation(s)" in output
        assert "pipelex/cogt/aggregator.py:3" in output
        assert "pipelex/cogt/sample/worker.py:42" in output
        assert HubLayeringViolationKind.INTERPRETER_HUB_TRANSITIVE.remedy in output

    def test_a_transitive_finding_alone_is_a_failure(self, mocker: MockerFixture, console_buffer: io.StringIO) -> None:
        """The pass that found the real breach must be able to fail the gate on its own."""
        transitive = HubLayeringViolation(
            relative_path="pipelex/providers/builtins.py",
            lineno=6,
            kind=HubLayeringViolationKind.INTERPRETER_HUB_TRANSITIVE,
            detail="reaches `pipelex.interpreter_hub` via pipelex.runtime_bridge.direct_orchestrator → pipelex.interpreter_hub",
        )
        _patch_scans(mocker, transitive=[transitive])

        with pytest.raises(SystemExit) as exit_info:
            check_hub_layering_cmd(quiet=True)

        assert exit_info.value.code == 1
        assert "pipelex/providers/builtins.py:6" in console_buffer.getvalue()

    def test_missing_scan_root_fails_without_scanning(self, mocker: MockerFixture, console_buffer: io.StringIO, tmp_path: Path) -> None:
        """A vanished scan root must never read as a pass: scanning nothing finds nothing."""
        mocker.patch.object(cmd_mod, "SCAN_ROOTS", (tmp_path / "ghost_root",))
        per_file_scan = mocker.patch.object(cmd_mod, "collect_all_violations", return_value=[])
        transitive_scan = mocker.patch.object(cmd_mod, "collect_transitive_violations", return_value=[])

        with pytest.raises(SystemExit) as exit_info:
            check_hub_layering_cmd(quiet=True)

        assert exit_info.value.code == 1
        assert "ghost_root" in console_buffer.getvalue()
        per_file_scan.assert_not_called()
        transitive_scan.assert_not_called()
