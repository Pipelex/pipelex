"""Unit tests for the agent-CLI bundle-validation failure surface (``agent_error_validate_bundle``).

Markdown renders the structured items as prose with a fix-aware footer; JSON keeps the exact
structured envelope (``is_valid`` / ``bundle_path`` / ``validation_errors`` + the unchanged hint).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
import typer

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.cli.agent_cli.commands.agent_output import (
    CliOutputFormat,
    _render_validate_bundle_markdown,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
    agent_error_validate_bundle,
    set_agent_cli_error_format,
)
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.suggested_fix import FixSafety, SuggestedFix

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def _fixable_item(*, source: Path) -> ValidationErrorItem:
    return ValidationErrorItem(
        category=ValidationErrorCategory.PIPE_VALIDATION,
        error_type="inadequate_output_multiplicity",
        pipe_code="brainstorm",
        domain_code="story_studio",
        source=str(source),
        message="the sequence declares 'StoryIdea' but its last step yields 'StoryIdea[]'.",
        suggested_fix=SuggestedFix(
            fix_code="match-sequence-output",
            description="Set output of pipe 'brainstorm' to 'StoryIdea[]' to match its last step",
            safety=FixSafety.SAFE,
            source=str(source),
            ops=[],
        ),
    )


class TestValidateBundleErrorFormat:
    @pytest.fixture(autouse=True)
    def _reset_error_format(self) -> Iterator[None]:
        # The error format is a process-global ContextVar; reset it after each test so a markdown
        # test can't leak into a later JSON-default test (mirrors the app callback's per-invocation reset).
        yield
        set_agent_cli_error_format(CliOutputFormat.JSON)

    def test_markdown_renders_prose_and_fix_aware_footer(self, tmp_path: Path) -> None:
        """Markdown renders a heading, the bundle, prose items with the 💡 fix line, and a fix-aware footer."""
        bundle_path = tmp_path / "bundle.mthds"
        markdown = _render_validate_bundle_markdown(
            [_fixable_item(source=bundle_path)],
            bundle_path=bundle_path,
            library_dirs=[tmp_path / "libs"],
            allow_signatures=False,
        )

        assert markdown.startswith("# Bundle validation failed")
        assert f"**Bundle:** `{bundle_path}`" in markdown
        assert "1. **Inadequate Output Multiplicity**" in markdown
        assert "   - 💡 Suggested fix: Set output of pipe 'brainstorm' to 'StoryIdea[]' to match its last step" in markdown
        # Disease E: the boilerplate hint is replaced by a fix-aware footer naming the exact command with -L echoed.
        assert "Check the validation_errors array" not in markdown
        assert f"💡 1 of these errors can be fixed automatically — run: `pipelex-agent fix bundle {bundle_path} -L {tmp_path / 'libs'}`" in markdown

    def test_markdown_no_fix_footer_when_nothing_fixable(self, tmp_path: Path) -> None:
        """With no suggested fix, the footer points at the messages instead of naming a fix command."""
        item = ValidationErrorItem(category=ValidationErrorCategory.BLUEPRINT_VALIDATION, message="something is wrong")

        markdown = _render_validate_bundle_markdown([item], bundle_path=tmp_path / "b.mthds", library_dirs=None, allow_signatures=False)

        assert "no automatic fix" in markdown
        assert "pipelex-agent fix bundle" not in markdown

    def test_markdown_dispatch_emits_prose_to_stderr(self, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        """In markdown mode the dispatcher prints prose (not JSON) to stderr and exits 1."""
        set_agent_cli_error_format(CliOutputFormat.MARKDOWN)
        exc = ValidateBundleError(message="Could not load blueprints because of: bad stuff")

        with pytest.raises(typer.Exit) as exc_info:
            agent_error_validate_bundle(exc, bundle_path=tmp_path / "b.mthds")

        assert exc_info.value.exit_code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith("# Bundle validation failed")
        with pytest.raises(json.JSONDecodeError):
            json.loads(captured.err)

    def test_json_dispatch_emits_unchanged_structured_envelope(self, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        """In JSON mode the dispatcher emits the byte-stable structured envelope hooks branch on."""
        set_agent_cli_error_format(CliOutputFormat.JSON)
        bundle_path = tmp_path / "b.mthds"
        exc = ValidateBundleError(message="no details")

        with pytest.raises(typer.Exit) as exc_info:
            agent_error_validate_bundle(exc, bundle_path=bundle_path)

        assert exc_info.value.exit_code == 1
        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error"] is True
        assert parsed["error_type"] == "ValidateBundleError"
        assert parsed["is_valid"] is False
        assert parsed["bundle_path"] == str(bundle_path)
        # The message-only residual makes the structured-info invariant total; the hint stays the JSON boilerplate.
        assert parsed["validation_errors"] == [{"category": "blueprint_validation", "message": "no details"}]
        assert parsed["hint"] == "Check the validation_errors array for specific issues"
