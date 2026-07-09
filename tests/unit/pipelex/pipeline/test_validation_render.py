"""Unit tests for the validate markdown renderers in `pipelex.pipeline.validation_render`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.pipeline.validation_render import (
    build_fix_command,
    format_validate_markdown,
    format_validation_error_items_markdown,
    render_invalid_validation_markdown,
)
from pipelex.suggested_fix import FixSafety, SuggestedFix


class TestValidationRender:
    def test_renders_pending_signatures_section_with_not_runnable_verdict(self):
        """A populated pending_signatures list renders the verbatim section heading, an explicit
        "NOT yet runnable" verdict, and each ref as a bullet.
        """
        result: dict[str, Any] = {
            "success": True,
            "bundle_path": "/fake/method.mthds",
            "validated_pipes": [{"pipe_ref": "research.research_brief", "status": "SUCCESS"}],
            "total_pipes": 1,
            "pending_signatures": ["research.find_key_findings", "research.rank_findings"],
            "is_runnable": False,
        }

        markdown = format_validate_markdown(result)

        assert markdown.startswith("# Validation passed")
        # Heading kept verbatim — a downstream plugin reads this exact string.
        assert "## Pending signatures (2)" in markdown
        # Explicit negative verdict, with the count, immediately above the list.
        assert "⚠️ This method is NOT yet runnable" in markdown
        assert "2 pipes are still `PipeSignature` placeholders" in markdown
        assert "- `research.find_key_findings`" in markdown
        assert "- `research.rank_findings`" in markdown
        # The verdict must precede the verbatim heading — consumers expect the note directly above it.
        assert markdown.index("⚠️ This method is NOT yet runnable") < markdown.index("## Pending signatures")

    def test_renders_single_pending_signature_with_singular_grammar(self):
        """A single pending signature renders grammatically — "1 pipe is still a `PipeSignature`
        placeholder" — with no "(s)", singular verb, and the article present.
        """
        result: dict[str, Any] = {
            "success": True,
            "bundle_path": "/fake/method.mthds",
            "validated_pipes": [{"pipe_ref": "research.research_brief", "status": "SUCCESS"}],
            "total_pipes": 1,
            "pending_signatures": ["research.find_key_findings"],
            "is_runnable": False,
        }

        markdown = format_validate_markdown(result)

        # The count line also pluralizes: a single validated pipe is "1 pipe", not "1 pipe(s)".
        assert "Validated 1 pipe:" in markdown
        assert "1 pipe is still a `PipeSignature` placeholder" in markdown
        assert "## Pending signatures (1)" in markdown
        # No "(s)" shorthand anywhere in the rendered markdown.
        assert "(s)" not in markdown

    def test_renders_runnable_verdict_for_complete_bundle(self):
        """A present-but-empty pending_signatures (complete bundle) renders an explicit runnable
        verdict and no "Pending signatures" section.
        """
        result: dict[str, Any] = {
            "success": True,
            "bundle_path": "/fake/method.mthds",
            "validated_pipes": [{"pipe_ref": "research.research_brief", "status": "SUCCESS"}],
            "total_pipes": 1,
            "pending_signatures": [],
            "is_runnable": True,
        }

        markdown = format_validate_markdown(result)

        assert markdown.startswith("# Validation passed")
        assert "✅ All pipes are concretely implemented" in markdown
        assert "this method is runnable." in markdown
        assert "Pending signatures" not in markdown

    def test_omits_runnability_verdict_when_key_absent(self):
        """The `validate all` / `validate pipe` shape omits the `pending_signatures` key entirely —
        so no runnability verdict (positive or negative) leaks onto those non-bundle surfaces.
        """
        without_key: dict[str, Any] = {
            "success": True,
            "validated_pipes": [{"pipe_ref": "research.research_brief", "status": "SUCCESS"}],
            "total_pipes": 1,
        }

        markdown = format_validate_markdown(without_key)

        assert markdown.startswith("# Validation passed")
        assert "Pending signatures" not in markdown
        assert "runnable" not in markdown
        assert "✅" not in markdown
        assert "⚠️" not in markdown

    def test_renders_invalid_report_with_locators_and_dry_run_residual(self):
        """The invalid-arm renderer surfaces the message, an error count, and each item's
        category + message with its present locators; a dry_run residual (no locators) renders too.
        """
        report: dict[str, Any] = {
            "is_valid": False,
            "message": "MTHDS validation found errors",
            "validation_errors": [
                {
                    "category": "pipe_validation",
                    "error_type": "PipeValidationError",
                    "message": "Pipe references an unknown concept.",
                    "pipe_code": "summarize",
                    "concept_code": "Contractt",
                    "field_name": "output",
                    "source": "/fake/method.mthds",
                },
                {
                    "category": "dry_run",
                    "error_type": "DryRunError",
                    "message": "Dry run failed: boom.",
                },
            ],
        }

        markdown = render_invalid_validation_markdown(report)

        assert markdown.startswith("# Validation failed")
        assert "MTHDS validation found errors" in markdown
        assert "## Errors (2)" in markdown
        assert "1. **pipe_validation** — Pipe references an unknown concept." in markdown
        assert "   - pipe: `summarize`" in markdown
        assert "   - concept: `Contractt`" in markdown
        assert "   - source: `/fake/method.mthds`" in markdown
        # The dry_run residual has no locators — it renders its category + message, no sub-bullets.
        assert "2. **dry_run** — Dry run failed: boom." in markdown

    def test_format_validation_error_items_markdown_groups_categories_and_renders_fix_line(self):
        """The shared items renderer groups by category, humanizes the error_type title, renders
        the identity fields + message + `💡 Suggested fix` line, and keeps the dry_run residual plain.
        """
        items = [
            ValidationErrorItem(
                category=ValidationErrorCategory.PIPE_VALIDATION,
                error_type="inadequate_output_multiplicity",
                pipe_code="brainstorm",
                domain_code="story_studio",
                source="/w/bundle.mthds",
                message="the sequence 'brainstorm' declares its output as 'StoryIdea', but its last step yields 'StoryIdea[]'.",
                suggested_fix=SuggestedFix(
                    fix_code="match-sequence-output",
                    description="Set output of pipe 'brainstorm' to 'StoryIdea[]' to match its last step",
                    safety=FixSafety.SAFE,
                    ops=[],
                ),
            ),
            ValidationErrorItem(
                category=ValidationErrorCategory.DRY_RUN,
                error_type="DryRunError",
                message="Dry run failed: boom.",
            ),
        ]

        markdown = format_validation_error_items_markdown(items)

        # Category grouping (markdown headings), humanized title, identity fields, message, fix line.
        assert "## Pipe validation errors" in markdown
        assert "1. **Inadequate Output Multiplicity**" in markdown
        assert "   - Pipe: `brainstorm`" in markdown
        assert "   - Domain: `story_studio`" in markdown
        assert "   - the sequence 'brainstorm' declares its output as 'StoryIdea'" in markdown
        assert "   - 💡 Suggested fix: Set output of pipe 'brainstorm' to 'StoryIdea[]' to match its last step" in markdown
        assert "   - Source: `/w/bundle.mthds`" in markdown
        # No internal repr / Python-list-repr brackets leak (Phase 1 diseases stay cured downstream).
        assert "multiplicity=None" not in markdown
        # The dry_run residual keeps its plain single-message rendering (no numbering, no bullets).
        assert "## Dry run error" in markdown
        assert "Dry run failed: boom." in markdown

    def test_build_fix_command_echoes_library_dirs_and_signatures(self):
        """`build_fix_command` shell-joins the executable, path, each `-L` dir, and `--allow-signatures`."""
        command = build_fix_command(
            "pipelex-agent",
            bundle_path=Path("my bundle.mthds"),
            library_dirs=[Path("libs/a"), Path("libs/b")],
            allow_signatures=True,
        )

        # shlex.join quotes the space-bearing path so it stays one argument when pasted.
        assert command == "pipelex-agent fix bundle 'my bundle.mthds' -L libs/a -L libs/b --allow-signatures"

    def test_build_fix_command_minimal_has_no_flags(self):
        """With no library dirs and signatures disabled, only the bare `fix bundle <path>` is emitted."""
        command = build_fix_command("pipelex", bundle_path=Path("bundle.mthds"))

        assert command == "pipelex fix bundle bundle.mthds"
