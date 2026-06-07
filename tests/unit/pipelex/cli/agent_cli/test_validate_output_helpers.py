"""Unit tests for the agent CLI validate markdown renderer (`format_validate_markdown`)."""

from __future__ import annotations

from typing import Any

from pipelex.cli.agent_cli.commands.validate._output_helpers import format_validate_markdown  # noqa: PLC2701


class TestFormatValidateMarkdown:
    def test_renders_pending_signatures_section_when_present(self):
        """A populated pending_signatures list produces a "Pending signatures" section listing each ref."""
        result: dict[str, Any] = {
            "success": True,
            "bundle_path": "/fake/method.mthds",
            "validated_pipes": [{"pipe_code": "research.research_brief", "status": "SUCCESS"}],
            "total_pipes": 1,
            "pending_signatures": ["research.find_key_findings", "research.rank_findings"],
        }

        markdown = format_validate_markdown(result)

        assert markdown.startswith("# Validation passed")
        assert "## Pending signatures (2)" in markdown
        assert "- `research.find_key_findings`" in markdown
        assert "- `research.rank_findings`" in markdown

    def test_omits_pending_section_when_empty_or_absent(self):
        """An empty (or missing) pending_signatures must not emit a "Pending signatures" section."""
        with_empty: dict[str, Any] = {
            "success": True,
            "validated_pipes": [{"pipe_code": "research.research_brief", "status": "SUCCESS"}],
            "total_pipes": 1,
            "pending_signatures": [],
        }
        without_key: dict[str, Any] = {
            "success": True,
            "validated_pipes": [{"pipe_code": "research.research_brief", "status": "SUCCESS"}],
            "total_pipes": 1,
        }

        assert "Pending signatures" not in format_validate_markdown(with_empty)
        assert "Pending signatures" not in format_validate_markdown(without_key)
