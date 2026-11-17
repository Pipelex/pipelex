"""Unit tests for _output_helpers: format_run_markdown()."""

from __future__ import annotations

import datetime
import json
import subprocess  # ruff: ignore[suspicious-subprocess-import]
from typing import TYPE_CHECKING, Any

import pytest
from kajson import kajson

from pipelex.cli.agent_cli.commands.run._output_helpers import format_run_markdown

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


class TestFormatRunMarkdown:
    """Tests for format_run_markdown()."""

    def test_rendered_markdown_is_used(self) -> None:
        """A non-empty main_stuff markdown is rendered verbatim under '## Result'."""
        result: dict[str, Any] = {
            "main_stuff": {"json": {"a": 1}, "markdown": "# Hello\n\nWorld", "html": ""},
            "working_memory": {"root": {}},
        }
        markdown = format_run_markdown(result, with_memory=True)
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
        markdown = format_run_markdown(result, with_memory=True)
        assert "## Result" in markdown
        assert "answer" in markdown, "the pipeline result must appear in the Result section"
        assert "42" in markdown
        assert "run-123" not in markdown, "envelope metadata must not stand in for the result"

    def test_no_main_stuff_falls_back_to_body(self) -> None:
        """A compact-shape result renders its concept JSON as the body."""
        result: dict[str, Any] = {"clauses": [{"id": 1, "text": "clause one"}]}
        markdown = format_run_markdown(result, with_memory=False)
        assert "## Result" in markdown
        assert "clauses" in markdown
        assert "clause one" in markdown

    def test_no_main_output_message(self) -> None:
        """An empty main_stuff with no other payload yields the explicit no-output message."""
        result: dict[str, Any] = {"main_stuff": {}, "working_memory": {"root": {}}}
        markdown = format_run_markdown(result, with_memory=True)
        assert "_The pipeline produced no main output._" in markdown

    def test_main_stuff_dict_without_json_does_not_leak_metadata(self) -> None:
        """A dict main_stuff lacking a json payload must not surface envelope metadata as the Result."""
        result: dict[str, Any] = {
            "main_stuff": {"markdown": "", "html": ""},
            "working_memory": {"root": {}},
            "pipeline_run_id": "run-456",
        }
        markdown = format_run_markdown(result, with_memory=True)
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
        markdown = format_run_markdown(result, with_memory=True)
        assert "## Result" in markdown
        assert '"answer": 42' in markdown, "the kajson string payload must be rendered as structured JSON"
        assert '\\"answer\\"' not in markdown, "the payload must be decoded, not escaped"
        assert "2024-01-02T03:04:05" in markdown, "kajson custom types must be reconstituted and cleanly rendered"
        assert "__class__" not in markdown, "kajson metadata must not leak into the rendered JSON"
        assert '"tzinfo"' not in markdown, "the datetime must render as an ISO string, not a raw tagged dict"

    def test_class_marker_payload_starts_no_process(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A `json` string naming `subprocess.Popen` through kajson class markers is rendered as plain data: the decoder
        never imports the module or calls the class, so no process starts and the marker file is never created.
        """
        marker_file = tmp_path / "MARK"
        popen_spy = mocker.spy(subprocess, "Popen")
        payload = json.dumps({"__class__": "Popen", "__module__": "subprocess", "args": ["touch", str(marker_file)]})
        result: dict[str, Any] = {
            "main_stuff": {"json": payload, "markdown": "", "html": ""},
            "working_memory": {},
        }
        markdown = format_run_markdown(result, with_memory=True)
        assert popen_spy.call_count == 0, "a class marker in the payload must never reach a constructor"
        assert not marker_file.exists(), "the payload must not start a process"
        assert "## Result" in markdown
        assert '"touch"' in markdown, "the payload's data must still be rendered"
        assert "__class__" not in markdown

    def test_nested_class_marker_payload_starts_no_process(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """The same gadget nested inside a list in an otherwise ordinary result starts no process either."""
        marker_file = tmp_path / "MARK"
        popen_spy = mocker.spy(subprocess, "Popen")
        gadget = {"__class__": "Popen", "__module__": "subprocess", "args": ["touch", str(marker_file)]}
        payload = json.dumps({"answer": 42, "items": [gadget]})
        result: dict[str, Any] = {
            "main_stuff": {"json": payload, "markdown": "", "html": ""},
            "working_memory": {},
        }
        markdown = format_run_markdown(result, with_memory=True)
        assert popen_spy.call_count == 0
        assert not marker_file.exists()
        assert '"answer": 42' in markdown

    @pytest.mark.parametrize(
        "marker",
        [
            {"__class__": "datetime", "__module__": "datetime", "datetime": "not a date"},
            {"__class__": "time", "__module__": "datetime", "time": "12:00:00"},
            {"__class__": "time", "__module__": "datetime", "time": "12:00:00.000000", "tzinfo": None, "utcoffset": 1e20},
            {"__class__": "datetime", "__module__": "datetime", "datetime": "2020-01-01 00:00:00.000000", "tzinfo": "UTC", "utcoffset": 1e20},
            {"__class__": "datetime", "__module__": "datetime", "datetime": "2020-01-01 00:00:00.000000", "tzinfo": "a" * 256, "utcoffset": None},
        ],
        ids=["unparseable_datetime", "time_without_fraction", "time_offset_overflow", "datetime_offset_overflow", "zone_name_too_long"],
    )
    def test_malformed_date_marker_is_rendered_as_data(self, marker: dict[str, Any]) -> None:
        """A date, datetime or time marker whose values kajson cannot parse is left as plain data rather than failing the render."""
        payload = json.dumps({"when": marker})
        result: dict[str, Any] = {
            "main_stuff": {"json": payload, "markdown": "", "html": ""},
            "working_memory": {},
        }
        markdown = format_run_markdown(result, with_memory=True)
        assert "## Result" in markdown
        assert "__class__" not in markdown

    def test_compact_result_keeps_fields_colliding_with_envelope_keys(self) -> None:
        """In compact mode the result IS the concept JSON; a concept field whose name collides with
        an envelope key (e.g. 'main_stuff') must survive into the rendered Result block.
        """
        result: dict[str, Any] = {"summary": "done", "main_stuff": "important value"}
        markdown = format_run_markdown(result, with_memory=False)
        assert "## Result" in markdown
        assert "important value" in markdown, "a concept field colliding with an envelope key must not be dropped"
        assert "summary" in markdown

    def test_compact_result_with_dict_valued_main_stuff_is_not_dropped(self) -> None:
        """A compact concept JSON carrying a dict-valued 'main_stuff' field must not be misread as
        the run envelope: with with_memory=False the result is rendered whole, not dropped as
        'no main output' just because a field happens to be named like an envelope key.
        """
        result: dict[str, Any] = {"summary": "done", "main_stuff": {"foo": "bar"}}
        markdown = format_run_markdown(result, with_memory=False)
        assert "## Result" in markdown
        assert "_The pipeline produced no main output._" not in markdown, "the real result must not be dropped"
        assert "foo" in markdown, "a dict-valued concept field must survive into the Result block"
        assert "bar" in markdown
        assert "summary" in markdown
