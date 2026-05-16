"""Unit tests for _output_helpers: format_run_markdown()."""

from __future__ import annotations

from typing import Any

from pipelex.cli.agent_cli.commands.run._output_helpers import format_run_markdown  # noqa: PLC2701


class TestFormatRunMarkdown:
    """Tests for format_run_markdown()."""

    def test_rendered_markdown_is_used(self) -> None:
        """A non-empty main_stuff markdown is rendered verbatim under '## Result'."""
        result: dict[str, Any] = {
            "main_stuff": {"json": {"a": 1}, "markdown": "# Hello\n\nWorld", "html": ""},
            "working_memory": {"root": {}},
        }
        markdown = format_run_markdown(result)
        assert "## Result" in markdown
        assert "# Hello" in markdown
        assert "World" in markdown

    def test_empty_markdown_falls_back_to_json_payload(self) -> None:
        """When main_stuff carries an empty markdown (API runner), the structured json payload is surfaced, not metadata."""
        result: dict[str, Any] = {
            "main_stuff": {"json": {"answer": 42}, "markdown": "", "html": ""},
            "working_memory": {"root": {}},
            "pipeline_run_id": "run-123",
        }
        markdown = format_run_markdown(result)
        assert "## Result" in markdown
        assert "answer" in markdown, "the pipeline result must appear in the Result section"
        assert "42" in markdown
        assert "run-123" not in markdown, "envelope metadata must not stand in for the result"

    def test_no_main_stuff_falls_back_to_body(self) -> None:
        """A compact-shape result with no main_stuff key renders its non-envelope keys as the body."""
        result: dict[str, Any] = {"clauses": [{"id": 1, "text": "clause one"}]}
        markdown = format_run_markdown(result)
        assert "## Result" in markdown
        assert "clauses" in markdown
        assert "clause one" in markdown

    def test_no_main_output_message(self) -> None:
        """An empty main_stuff with no other payload yields the explicit no-output message."""
        result: dict[str, Any] = {"main_stuff": {}, "working_memory": {"root": {}}}
        markdown = format_run_markdown(result)
        assert "_The pipeline produced no main output._" in markdown
