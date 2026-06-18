"""Unit tests for the validate markdown renderers in `pipelex.pipeline.validation_render`."""

from __future__ import annotations

from typing import Any

from pipelex.pipeline.validation_render import format_validate_markdown, render_invalid_validation_markdown


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
