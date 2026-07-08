"""Unit tests for the human ``pipelex fix bundle`` rendering and argument handling.

Mirrors the agent-side ``test_fix_format.py``: the fix loop is patched with a canned
``FixBundleResult`` per verdict arm, and the Rich output is recorded through a plain-text
console. Covers all verdict arms of D5.4 plus the ``--select``/``--ignore`` validation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import typer
from rich.console import Console

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.cli.commands.fix.bundle_cmd import fix_bundle_cmd
from pipelex.pipeline.fixes.fix_loop import FixBundleResult
from pipelex.suggested_fix import FixSafety, SuggestedFix

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

FIX_CORE_MODULE = "pipelex.cli.commands.fix._fix_core"


def _applied_fix(source: str | None) -> SuggestedFix:
    return SuggestedFix(
        fix_code="match-sequence-output",
        description="Set output of pipe 'list_ideas' to 'Idea[]' to match its last step",
        safety=FixSafety.SAFE,
        source=source,
        ops=[],
    )


def _remaining_item(source: str) -> ValidationErrorItem:
    return ValidationErrorItem(
        category=ValidationErrorCategory.PIPE_VALIDATION,
        error_type="MISSING_CONCEPT",
        pipe_code="say_hi",
        message="concept 'MissingConcept' is not declared",
        source=source,
    )


class TestFixBundleHumanFormat:
    @pytest.fixture
    def console(self, mocker: MockerFixture) -> Console:
        """Recorded plain-text console patched into the fix core module."""
        recorded_console = Console(width=500, record=True, color_system=None)
        mocker.patch(f"{FIX_CORE_MODULE}.get_console", return_value=recorded_console)
        return recorded_console

    def _patch_command(self, mocker: MockerFixture, *, result: FixBundleResult) -> None:
        mocker.patch(f"{FIX_CORE_MODULE}.make_pipelex_for_cli")
        mocker.patch(f"{FIX_CORE_MODULE}.Pipelex.teardown_if_needed")
        mocker.patch(f"{FIX_CORE_MODULE}.get_telemetry_manager", return_value=mocker.MagicMock())
        mocker.patch(f"{FIX_CORE_MODULE}.tag")
        mocker.patch(f"{FIX_CORE_MODULE}.fix_bundle_file", new=mocker.AsyncMock(return_value=result))

    def _bundle_file(self, tmp_path: Path) -> Path:
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text('domain = "fix_human_format"\n', encoding="utf-8")
        return bundle_path

    def test_fixed_valid_names_every_change_and_exits_zero(self, tmp_path: Path, mocker: MockerFixture, console: Console) -> None:
        bundle_path = self._bundle_file(tmp_path)
        result = FixBundleResult(
            is_valid=True,
            iterations=1,
            fixes_applied=[_applied_fix(str(bundle_path))],
            files_written=[str(bundle_path.resolve())],
            remaining_errors=[],
            pending_signatures=[],
            is_runnable=True,
        )
        self._patch_command(mocker, result=result)

        fix_bundle_cmd(path=str(bundle_path))

        output = console.export_text()
        assert "✅ Bundle fixed — valid" in output
        assert f"Bundle: {bundle_path}" in output
        assert "1. Set output of pipe 'list_ideas' to 'Idea[]' to match its last step (match-sequence-output)" in output
        assert "Files written:" in output
        assert str(bundle_path.resolve()) in output
        assert "Iterations: 1" in output

    def test_fix_sourced_at_another_file_names_that_file(self, tmp_path: Path, mocker: MockerFixture, console: Console) -> None:
        bundle_path = self._bundle_file(tmp_path)
        library_file = tmp_path / "library.mthds"
        library_file.write_text('domain = "library"\n', encoding="utf-8")
        result = FixBundleResult(
            is_valid=True,
            iterations=1,
            fixes_applied=[_applied_fix(str(library_file))],
            files_written=[str(library_file.resolve())],
            remaining_errors=[],
            pending_signatures=[],
            is_runnable=True,
        )
        self._patch_command(mocker, result=result)

        fix_bundle_cmd(path=str(bundle_path))

        output = console.export_text()
        assert f"(match-sequence-output) — {library_file}" in output

    def test_already_valid_exits_zero(self, tmp_path: Path, mocker: MockerFixture, console: Console) -> None:
        bundle_path = self._bundle_file(tmp_path)
        result = FixBundleResult(
            is_valid=True,
            iterations=0,
            fixes_applied=[],
            files_written=[],
            remaining_errors=[],
            pending_signatures=[],
            is_runnable=True,
        )
        self._patch_command(mocker, result=result)

        fix_bundle_cmd(path=str(bundle_path))

        output = console.export_text()
        assert "✅ Bundle already valid" in output
        assert "Applied fixes:" not in output
        assert "Iterations:" not in output

    def test_valid_not_runnable_without_allow_signatures_exits_one(self, tmp_path: Path, mocker: MockerFixture, console: Console) -> None:
        bundle_path = self._bundle_file(tmp_path)
        result = FixBundleResult(
            is_valid=True,
            iterations=0,
            fixes_applied=[],
            files_written=[],
            remaining_errors=[],
            pending_signatures=["fix_human_format.pending_pipe"],
            is_runnable=False,
        )
        self._patch_command(mocker, result=result)

        with pytest.raises(typer.Exit) as exc_info:
            fix_bundle_cmd(path=str(bundle_path))

        assert exc_info.value.exit_code == 1
        output = console.export_text()
        assert "NOT yet runnable" in output
        assert "fix_human_format.pending_pipe" in output
        assert "--allow-signatures" in output

    def test_valid_not_runnable_with_allow_signatures_exits_zero(self, tmp_path: Path, mocker: MockerFixture, console: Console) -> None:
        bundle_path = self._bundle_file(tmp_path)
        result = FixBundleResult(
            is_valid=True,
            iterations=0,
            fixes_applied=[],
            files_written=[],
            remaining_errors=[],
            pending_signatures=["fix_human_format.pending_pipe"],
            is_runnable=False,
        )
        self._patch_command(mocker, result=result)

        fix_bundle_cmd(path=str(bundle_path), allow_signatures=True)

        output = console.export_text()
        assert "✅ Bundle already valid" in output
        assert "Pending PipeSignature placeholder(s): fix_human_format.pending_pipe" in output
        assert "NOT yet runnable" not in output

    def test_still_invalid_shows_partial_progress_bail_reason_and_remaining_errors(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        console: Console,
    ) -> None:
        bundle_path = self._bundle_file(tmp_path)
        result = FixBundleResult(
            is_valid=False,
            iterations=2,
            fixes_applied=[_applied_fix(str(bundle_path))],
            files_written=[str(bundle_path.resolve())],
            remaining_errors=[_remaining_item(str(bundle_path))],
            bail_reason="no progress: every proposed fix fingerprint was already applied",
        )
        self._patch_command(mocker, result=result)

        with pytest.raises(typer.Exit) as exc_info:
            fix_bundle_cmd(path=str(bundle_path))

        assert exc_info.value.exit_code == 1
        output = console.export_text()
        assert "❌ Bundle could not be fully fixed" in output
        assert "1. Set output of pipe 'list_ideas' to 'Idea[]' to match its last step (match-sequence-output)" in output
        assert "Stopped: no progress" in output
        assert "Remaining errors:" in output
        assert "Pipe Validation Errors:" in output
        assert "concept 'MissingConcept' is not declared" in output
        assert "💡 Tip:" in output

    @pytest.mark.usefixtures("console")
    def test_file_not_found_exits_two(self, tmp_path: Path, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        bundle_path = self._bundle_file(tmp_path)
        mocker.patch(f"{FIX_CORE_MODULE}.make_pipelex_for_cli")
        mocker.patch(f"{FIX_CORE_MODULE}.Pipelex.teardown_if_needed")
        mocker.patch(f"{FIX_CORE_MODULE}.get_telemetry_manager", return_value=mocker.MagicMock())
        mocker.patch(f"{FIX_CORE_MODULE}.tag")
        mocker.patch(f"{FIX_CORE_MODULE}.fix_bundle_file", new=mocker.AsyncMock(side_effect=FileNotFoundError("missing")))

        with pytest.raises(typer.Exit) as exc_info:
            fix_bundle_cmd(path=str(bundle_path))

        assert exc_info.value.exit_code == 2
        assert "bundle file not found" in capsys.readouterr().err

    @pytest.mark.usefixtures("console")
    def test_unexpected_exception_exits_two(self, tmp_path: Path, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        bundle_path = self._bundle_file(tmp_path)
        mocker.patch(f"{FIX_CORE_MODULE}.make_pipelex_for_cli")
        mocker.patch(f"{FIX_CORE_MODULE}.Pipelex.teardown_if_needed")
        mocker.patch(f"{FIX_CORE_MODULE}.get_telemetry_manager", return_value=mocker.MagicMock())
        mocker.patch(f"{FIX_CORE_MODULE}.tag")
        mocker.patch(f"{FIX_CORE_MODULE}.fix_bundle_file", new=mocker.AsyncMock(side_effect=RuntimeError("boom")))

        with pytest.raises(typer.Exit) as exc_info:
            fix_bundle_cmd(path=str(bundle_path))

        assert exc_info.value.exit_code == 2
        assert "Failed to fix: boom" in capsys.readouterr().err

    def test_select_and_ignore_are_mutually_exclusive(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            fix_bundle_cmd(
                path="unused.mthds",
                select_codes_raw=["match-sequence-output"],
                ignore_codes_raw=["strip-namespace"],
            )

        assert exc_info.value.exit_code == 2
        assert "mutually exclusive" in capsys.readouterr().err

    def test_unknown_fix_code_is_rejected_listing_known_codes(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            fix_bundle_cmd(path="unused.mthds", select_codes_raw=["typo-rule"])

        assert exc_info.value.exit_code == 2
        err = capsys.readouterr().err
        assert "unknown fix rule code(s): typo-rule" in err
        assert "match-sequence-output" in err
