from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
import typer

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.cli.agent_cli.commands.agent_output import (
    CliOutputFormat,
    agent_error_validate_bundle,
    set_agent_cli_error_format,
)
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.suggested_fix import FixSafety, SetKeyOp, SuggestedFix
from pipelex.validation_error_types import PipeValidationErrorType

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


def _fixable_item(*, source: Path) -> ValidationErrorItem:
    return ValidationErrorItem(
        category=ValidationErrorCategory.PIPE_VALIDATION,
        error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY,
        pipe_code="brainstorm",
        domain_code="story_studio",
        source=str(source),
        message="the sequence declares 'StoryIdea' but its last step yields 'StoryIdea[]'.",
        suggested_fix=SuggestedFix(
            fix_code="match-sequence-output",
            description="Set output of pipe 'brainstorm' to 'StoryIdea[]' to match its last step",
            safety=FixSafety.SAFE,
            source=str(source),
            ops=[SetKeyOp(table_path=["pipe", "brainstorm"], key="output", value="StoryIdea[]")],
        ),
    )


def _unsafe_fixable_item(*, source: Path) -> ValidationErrorItem:
    return ValidationErrorItem(
        category=ValidationErrorCategory.PIPE_VALIDATION,
        error_type=PipeValidationErrorType.UNKNOWN_MODEL,
        pipe_code="write_tide_note",
        domain_code="tide_tables",
        source=str(source),
        field_name="model",
        message="Pipe 'write_tide_note' (PipeLLM), field 'model': Alias 'best-sonet' was not found in the model deck",
        suggested_fix=SuggestedFix(
            fix_code="rename-model",
            description="Replace model '@best-sonet' of pipe 'write_tide_note' with '@best-gpt', its one close match in the model deck",
            safety=FixSafety.UNSAFE,
            source=str(source),
            ops=[SetKeyOp(table_path=["pipe", "write_tide_note"], key="model", value="@best-gpt")],
        ),
    )


class TestValidateBundleErrorFormat:
    def _report_markdown(
        self,
        *,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        items: list[ValidationErrorItem],
        bundle_path: Path,
        library_dirs: list[Path] | None,
    ) -> str:
        """The Markdown ``agent_error_validate_bundle`` prints for a verdict whose items are ``items``."""
        set_agent_cli_error_format(CliOutputFormat.MARKDOWN)
        exc = ValidateBundleError(message="the bundle does not validate")
        mocker.patch.object(exc, "validation_error_items", return_value=items)
        with pytest.raises(typer.Exit) as exc_info:
            agent_error_validate_bundle(exc, bundle_path=bundle_path, library_dirs=library_dirs)
        assert exc_info.value.exit_code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        return captured.err

    def test_markdown_renders_prose_and_fix_aware_footer(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        """Markdown renders the problem's heading and facts, prose items with the 💡 fix line, the bundle, and a fix-aware footer."""
        bundle_path = tmp_path / "bundle.mthds"
        markdown = self._report_markdown(
            mocker=mocker, capsys=capsys, items=[_fixable_item(source=bundle_path)], bundle_path=bundle_path, library_dirs=[tmp_path / "libs"]
        )

        assert markdown.startswith("## The method does not validate")
        assert "- Code: `method.invalid` (domain method, retry no)" in markdown
        assert "1. **Inadequate Output Multiplicity**" in markdown
        assert "   - 💡 Suggested fix: Set output of pipe 'brainstorm' to 'StoryIdea[]' to match its last step" in markdown
        assert f"- **bundle_path:** {bundle_path}" in markdown
        assert "is_valid" not in markdown
        assert f"💡 1 of these errors can be fixed automatically — run: `pipelex-agent fix bundle {bundle_path} -L {tmp_path / 'libs'}`" in markdown
        with pytest.raises(json.JSONDecodeError):
            json.loads(markdown)

    def test_markdown_says_an_unsafe_fix_needs_confirmation(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        """A safe fix keeps the plain 💡 line; an unsafe one says it is unsafe, and the footer counts only the safe one."""
        bundle_path = tmp_path / "bundle.mthds"
        markdown = self._report_markdown(
            mocker=mocker,
            capsys=capsys,
            items=[_fixable_item(source=bundle_path), _unsafe_fixable_item(source=bundle_path)],
            bundle_path=bundle_path,
            library_dirs=None,
        )

        assert "   - 💡 Suggested fix: Set output of pipe 'brainstorm' to 'StoryIdea[]' to match its last step" in markdown
        assert (
            "   - 💡 Suggested fix (unsafe, confirm before applying): Replace model '@best-sonet' of pipe 'write_tide_note' with '@best-gpt'"
        ) in markdown
        assert "💡 Suggested fix: Replace model" not in markdown
        assert "💡 1 of these errors can be fixed automatically" in markdown

    def test_markdown_no_fix_footer_when_nothing_fixable(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        """With no suggested fix, the footer points at the messages instead of naming a fix command."""
        item = ValidationErrorItem(category=ValidationErrorCategory.BLUEPRINT_VALIDATION, message="something is wrong")

        markdown = self._report_markdown(mocker=mocker, capsys=capsys, items=[item], bundle_path=tmp_path / "b.mthds", library_dirs=None)

        assert "no automatic fix" in markdown
        assert "pipelex-agent fix bundle" not in markdown

    def test_json_is_the_method_s_problem_with_the_verdict_beside_it(self, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        """In JSON the verdict is the problem a hook branches on: its code and errors, with is_valid and the bundle beside them."""
        set_agent_cli_error_format(CliOutputFormat.JSON)
        bundle_path = tmp_path / "b.mthds"
        exc = ValidateBundleError(message="no details")

        with pytest.raises(typer.Exit) as exc_info:
            agent_error_validate_bundle(exc, bundle_path=bundle_path)

        assert exc_info.value.exit_code == 1
        parsed = json.loads(capsys.readouterr().err)
        assert parsed["code"] == "method.invalid"
        assert parsed["domain"] == "method"
        assert parsed["next_step"]["kind"] == "change_method"
        assert parsed["is_valid"] is False
        assert parsed["bundle_path"] == str(bundle_path)
        # The message-only residual makes the structured-info invariant total: one item, never an empty list.
        assert [(item["code"], item["params"]["finding"]) for item in parsed["errors"]] == [("method.schema_violation", "no details")]
        for retired in ("error", "error_type", "hint", "validation_errors"):
            assert retired not in parsed
