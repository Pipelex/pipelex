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
from pipelex.cli.commands.fix._diff_sandbox import PreviewSandbox  # noqa: PLC2701
from pipelex.cli.commands.fix._fix_core import _remap_result_to_originals  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
from pipelex.cli.commands.fix.bundle_cmd import fix_bundle_cmd
from pipelex.pipeline.fixes.fix_loop import FixBundleResult
from pipelex.suggested_fix import FixSafety, SuggestedFix
from pipelex.validation_error_types import PipeValidationErrorType

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
        error_type=PipeValidationErrorType.UNRESOLVED_CONCEPT,
        pipe_code="say_hi",
        message="concept 'MissingConcept' is not declared",
        source=source,
    )


def _fixable_remaining_item(source: str) -> ValidationErrorItem:
    """A remaining error that still carries a suggested fix — e.g. skipped by --select/--ignore or left out of write scope."""
    return ValidationErrorItem(
        category=ValidationErrorCategory.PIPE_VALIDATION,
        error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
        pipe_code="list_ideas",
        message="output concept does not match the last step",
        source=source,
        suggested_fix=_applied_fix(source),
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
        # The remaining error has no suggested fix, so the manual-edit tip is correct here.
        assert "no deterministic safe fix" in output

    def test_still_invalid_with_a_suggested_fix_remaining_does_not_claim_no_safe_fix(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        console: Console,
    ) -> None:
        """A remaining error still showing a 💡 suggested fix (skipped/out-of-scope) must not be told it has 'no deterministic safe fix'."""
        bundle_path = self._bundle_file(tmp_path)
        result = FixBundleResult(
            is_valid=False,
            iterations=0,
            fixes_applied=[],
            files_written=[],
            remaining_errors=[_fixable_remaining_item(str(bundle_path))],
        )
        self._patch_command(mocker, result=result)

        with pytest.raises(typer.Exit) as exc_info:
            fix_bundle_cmd(path=str(bundle_path))

        assert exc_info.value.exit_code == 1
        output = console.export_text()
        assert "💡 Suggested fix:" in output
        assert "no deterministic safe fix" not in output
        assert "still show a suggested fix" in output

    def test_diff_preview_pending_signatures_uses_conditional_phrasing(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        console: Console,
    ) -> None:
        """--diff on a bundle that would converge to valid-but-not-runnable must not assert the on-disk bundle IS valid."""
        bundle_path = self._bundle_file(tmp_path)

        def fake_loop(entry_path: Path, **_kwargs: object) -> FixBundleResult:
            entry_path.write_text('domain = "fix_human_format"\nmain_pipe = "list_ideas"\n', encoding="utf-8")
            return FixBundleResult(
                is_valid=True,
                iterations=1,
                fixes_applied=[_applied_fix(str(entry_path))],
                files_written=[str(entry_path.resolve())],
                remaining_errors=[],
                pending_signatures=["fix_human_format.pending_pipe"],
                is_runnable=False,
            )

        mocker.patch(f"{FIX_CORE_MODULE}.make_pipelex_for_cli")
        mocker.patch(f"{FIX_CORE_MODULE}.Pipelex.teardown_if_needed")
        mocker.patch(f"{FIX_CORE_MODULE}.get_telemetry_manager", return_value=mocker.MagicMock())
        mocker.patch(f"{FIX_CORE_MODULE}.tag")
        mocker.patch(f"{FIX_CORE_MODULE}.fix_bundle_file", new=mocker.AsyncMock(side_effect=fake_loop))

        with pytest.raises(typer.Exit) as exc_info:
            fix_bundle_cmd(path=str(bundle_path), diff=True)

        assert exc_info.value.exit_code == 1
        output = console.export_text()
        assert "would be valid but still NOT runnable" in output
        assert "fix_human_format.pending_pipe" in output
        assert "Bundle is valid but NOT yet runnable" not in output

    def test_preview_result_remaps_filesystem_error_paths_without_rewriting_semantic_paths(self, tmp_path: Path) -> None:
        """Remaining diagnostics must not retain deleted sandbox paths in structured fields or messages."""
        original_path = (tmp_path / "bundle.mthds").resolve()
        sandbox_path = (tmp_path / "pipelex-fix-preview-test" / "entry" / "bundle.mthds").resolve()
        sandbox = PreviewSandbox(
            entry_path=sandbox_path,
            library_dirs=[],
            writable_library_dirs=[],
            dir_mappings=[],
            entry_mapping=(sandbox_path, original_path),
        )
        filesystem_item = ValidationErrorItem(
            category=ValidationErrorCategory.PIPE_VALIDATION,
            message=f"Validation failed in file '{sandbox_path}'",
            source=str(sandbox_path),
            field_path=str(sandbox_path),
        )
        semantic_item = ValidationErrorItem(
            category=ValidationErrorCategory.BLUEPRINT_VALIDATION,
            message="Output declaration is invalid",
            source=str(sandbox_path),
            field_path="pipe → output",
        )
        result = FixBundleResult(
            is_valid=False,
            iterations=0,
            fixes_applied=[],
            remaining_errors=[filesystem_item, semantic_item],
        )

        remapped = _remap_result_to_originals(result, sandbox=sandbox)

        assert remapped.remaining_errors[0].source == str(original_path)
        assert remapped.remaining_errors[0].field_path == str(original_path)
        assert remapped.remaining_errors[0].message == f"Validation failed in file '{original_path}'"
        assert remapped.remaining_errors[1].source == str(original_path)
        assert remapped.remaining_errors[1].field_path == "pipe → output"

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

    @pytest.mark.usefixtures("console")
    def test_setup_failure_exits_two_and_tears_down(self, tmp_path: Path, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        bundle_path = self._bundle_file(tmp_path)
        mocker.patch(f"{FIX_CORE_MODULE}.make_pipelex_for_cli", side_effect=RuntimeError("setup exploded"))
        teardown_mock = mocker.patch(f"{FIX_CORE_MODULE}.Pipelex.teardown_if_needed")

        with pytest.raises(typer.Exit) as exc_info:
            fix_bundle_cmd(path=str(bundle_path))

        assert exc_info.value.exit_code == 2
        assert "Failed to fix: setup exploded" in capsys.readouterr().err
        teardown_mock.assert_called_once_with()

    def test_diff_previews_changes_without_writing_and_labels_would_be(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        console: Console,
    ) -> None:
        """--diff runs the loop against a sandbox copy: the diff and labels name the ORIGINAL path, the original is untouched."""
        bundle_path = self._bundle_file(tmp_path)
        original_content = bundle_path.read_text(encoding="utf-8")

        def fake_loop(entry_path: Path, **_kwargs: object) -> FixBundleResult:
            entry_path.write_text('domain = "fix_human_format"\nmain_pipe = "list_ideas"\n', encoding="utf-8")
            return FixBundleResult(
                is_valid=True,
                iterations=1,
                fixes_applied=[_applied_fix(str(entry_path))],
                files_written=[str(entry_path.resolve())],
                remaining_errors=[],
                pending_signatures=[],
                is_runnable=True,
            )

        mocker.patch(f"{FIX_CORE_MODULE}.make_pipelex_for_cli")
        mocker.patch(f"{FIX_CORE_MODULE}.Pipelex.teardown_if_needed")
        mocker.patch(f"{FIX_CORE_MODULE}.get_telemetry_manager", return_value=mocker.MagicMock())
        mocker.patch(f"{FIX_CORE_MODULE}.tag")
        mocker.patch(f"{FIX_CORE_MODULE}.fix_bundle_file", new=mocker.AsyncMock(side_effect=fake_loop))

        fix_bundle_cmd(path=str(bundle_path), diff=True)

        assert bundle_path.read_text(encoding="utf-8") == original_content
        output = console.export_text()
        assert "Preview (--diff): no files were written." in output
        assert f"--- {bundle_path.resolve()}" in output
        assert f"+++ {bundle_path.resolve()} (fixed)" in output
        assert '+main_pipe = "list_ideas"' in output
        assert "✅ Fix preview — these fixes would make the bundle valid" in output
        assert "Fixes that would be applied:" in output
        assert "Files that would be written:" in output
        assert f"- {bundle_path.resolve()}" in output
        assert "Files written:" not in output.replace("Files that would be written:", "")

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
