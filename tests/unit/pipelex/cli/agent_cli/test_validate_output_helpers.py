"""Unit tests for the agent CLI validate markdown renderer (`format_validate_markdown`)."""

from __future__ import annotations

from typing import Any

from pipelex.cli.agent_cli.commands.validate._output_helpers import format_validate_markdown  # noqa: PLC2701


class TestFormatValidateMarkdown:
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
        assert "2 pipe(s) are still `PipeSignature` placeholders" in markdown
        assert "- `research.find_key_findings`" in markdown
        assert "- `research.rank_findings`" in markdown
        # The verdict must precede the verbatim heading — consumers expect the note directly above it.
        assert markdown.index("⚠️ This method is NOT yet runnable") < markdown.index("## Pending signatures")

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
