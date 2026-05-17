"""Unit tests for _output_helpers: format_run_markdown()."""

from __future__ import annotations

import datetime
from typing import Any

from kajson import kajson

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

    def test_main_stuff_dict_without_json_does_not_leak_metadata(self) -> None:
        """A dict main_stuff lacking a json payload must not surface envelope metadata as the Result."""
        result: dict[str, Any] = {
            "main_stuff": {"markdown": "", "html": ""},
            "working_memory": {"root": {}},
            "pipeline_run_id": "run-456",
        }
        markdown = format_run_markdown(result)
        assert "_The pipeline produced no main output._" in markdown
        assert "run-456" not in markdown, "envelope metadata must not stand in for a missing result"

    def test_empty_markdown_with_kajson_string_payload_is_decoded(self) -> None:
        """When main_stuff['json'] is a kajson-encoded string (local runner shape), it is decoded
        with kajson so the Result block shows structured JSON — not an escaped quoted string — and
        custom types are reconstituted and rendered cleanly rather than left as raw tagged dicts.
        """
        payload = kajson.dumps({"answer": 42, "when": datetime.datetime(2024, 1, 2, 3, 4, 5)})
        result: dict[str, Any] = {
            "main_stuff": {"json": payload, "markdown": "", "html": ""},
            "working_memory": {"root": {}},
        }
        markdown = format_run_markdown(result)
        assert "## Result" in markdown
        assert '"answer": 42' in markdown, "the kajson string payload must be rendered as structured JSON"
        assert '\\"answer\\"' not in markdown, "the payload must be decoded, not escaped"
        assert "2024-01-02T03:04:05" in markdown, "kajson custom types must be reconstituted and cleanly rendered"
        assert "__class__" not in markdown, "kajson metadata must not leak into the rendered JSON"
        assert '"tzinfo"' not in markdown, "the datetime must render as an ISO string, not a raw tagged dict"

    def test_compact_result_keeps_fields_colliding_with_envelope_keys(self) -> None:
        """In compact mode the result IS the concept JSON; a concept field whose name collides with
        an envelope key (e.g. 'main_stuff') must survive into the rendered Result block.
        """
        result: dict[str, Any] = {"summary": "done", "main_stuff": "important value"}
        markdown = format_run_markdown(result)
        assert "## Result" in markdown
        assert "important value" in markdown, "a concept field colliding with an envelope key must not be dropped"
        assert "summary" in markdown
