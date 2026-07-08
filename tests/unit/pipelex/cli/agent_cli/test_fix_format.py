"""Unit tests for the agent CLI fix command format and argument handling."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
import typer

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.fix.bundle_cmd import fix_bundle_cmd
from pipelex.pipeline.fixes.fix_loop import FixBundleResult
from pipelex.suggested_fix import FixSafety, SuggestedFix

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

FIX_BUNDLE_MODULE = "pipelex.cli.agent_cli.commands.fix.bundle_cmd"


def _applied_fix(source: str) -> SuggestedFix:
    return SuggestedFix(
        fix_code="match-sequence-output",
        description="Set output of pipe 'list_ideas' to 'Idea[]'",
        safety=FixSafety.SAFE,
        source=source,
        ops=[],
    )


def _invalid_item(source: str) -> ValidationErrorItem:
    return ValidationErrorItem(
        category=ValidationErrorCategory.PIPE_VALIDATION,
        error_type="INADEQUATE_OUTPUT_CONCEPT",
        message="output mismatch",
        source=source,
    )


def _patch_command(
    mocker: MockerFixture,
    *,
    result: FixBundleResult,
) -> None:
    mocker.patch(f"{FIX_BUNDLE_MODULE}.make_pipelex_for_agent_cli")
    mocker.patch(f"{FIX_BUNDLE_MODULE}.Pipelex.teardown_if_needed")
    mocker.patch(f"{FIX_BUNDLE_MODULE}.fix_bundle_file", new=mocker.AsyncMock(return_value=result))


class TestFixFormat:
    def test_fix_markdown_is_default(self, tmp_path: Path, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text('domain = "fix_format"\n', encoding="utf-8")
        result = FixBundleResult(
            is_valid=True,
            iterations=1,
            fixes_applied=[_applied_fix(str(bundle_path))],
            files_written=[str(bundle_path.resolve())],
            remaining_errors=[],
        )
        _patch_command(mocker, result=result)

        fix_bundle_cmd(path=str(bundle_path))

        out = capsys.readouterr().out
        assert out.startswith("# Fix applied - bundle is valid")
        assert "`match-sequence-output`" in out
        with pytest.raises(json.JSONDecodeError):
            json.loads(out)

    def test_fix_json_with_format_json(self, tmp_path: Path, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text('domain = "fix_format"\n', encoding="utf-8")
        result = FixBundleResult(
            is_valid=True,
            iterations=0,
            fixes_applied=[],
            files_written=[],
            remaining_errors=[],
        )
        _patch_command(mocker, result=result)

        fix_bundle_cmd(path=str(bundle_path), output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["success"] is True
        assert parsed["is_valid"] is True
        assert parsed["bundle_path"] == str(bundle_path.resolve())

    def test_non_runnable_success_exits_one_after_json_payload(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text('domain = "fix_format"\n', encoding="utf-8")
        result = FixBundleResult(
            is_valid=True,
            iterations=0,
            fixes_applied=[],
            files_written=[],
            remaining_errors=[],
            pending_signatures=["fix_format.pending_pipe"],
            is_runnable=False,
        )
        _patch_command(mocker, result=result)

        with pytest.raises(typer.Exit) as exc_info:
            fix_bundle_cmd(path=str(bundle_path), output_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1
        captured = capsys.readouterr()
        assert captured.err == ""
        parsed = json.loads(captured.out)
        assert parsed["success"] is True
        assert parsed["is_valid"] is True
        assert parsed["is_runnable"] is False
        assert parsed["pending_signatures"] == ["fix_format.pending_pipe"]

    def test_allow_signatures_tolerates_non_runnable_success(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text('domain = "fix_format"\n', encoding="utf-8")
        result = FixBundleResult(
            is_valid=True,
            iterations=0,
            fixes_applied=[],
            files_written=[],
            remaining_errors=[],
            pending_signatures=["fix_format.pending_pipe"],
            is_runnable=False,
        )
        _patch_command(mocker, result=result)

        fix_bundle_cmd(path=str(bundle_path), allow_signatures=True, output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["success"] is True
        assert parsed["is_runnable"] is False
        assert parsed["pending_signatures"] == ["fix_format.pending_pipe"]

    def test_still_invalid_emits_json_error(self, tmp_path: Path, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text('domain = "fix_format"\n', encoding="utf-8")
        result = FixBundleResult(
            is_valid=False,
            iterations=1,
            fixes_applied=[_applied_fix(str(bundle_path))],
            files_written=[str(bundle_path.resolve())],
            remaining_errors=[_invalid_item(str(bundle_path))],
            bail_reason="no safe fixes remain",
        )
        _patch_command(mocker, result=result)

        with pytest.raises(typer.Exit) as exc_info:
            fix_bundle_cmd(path=str(bundle_path), output_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1
        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error"] is True
        assert parsed["error_type"] == "FixBundleError"
        assert parsed["is_valid"] is False
        assert parsed["bail_reason"] == "no safe fixes remain"
        assert parsed["remaining_errors"][0]["source"] == str(bundle_path)

    def test_select_and_ignore_are_mutually_exclusive(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            fix_bundle_cmd(
                path="unused.mthds",
                select_codes_raw=["match-sequence-output"],
                ignore_codes_raw=["strip-namespace"],
                output_format=CliOutputFormat.JSON,
            )

        assert exc_info.value.exit_code == 2
        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error_type"] == "ArgumentError"
        assert "mutually exclusive" in parsed["message"]

    def test_unknown_fix_code_is_rejected(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            fix_bundle_cmd(path="unused.mthds", select_codes_raw=["typo-rule"], output_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 2
        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error_type"] == "ArgumentError"
        assert parsed["unknown_fix_codes"] == ["typo-rule"]
        assert "match-sequence-output" in parsed["known_fix_codes"]
