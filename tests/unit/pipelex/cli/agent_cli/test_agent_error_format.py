"""Unit tests for format-aware agent CLI error output."""

from __future__ import annotations

import json

import pytest
import typer

from pipelex.cli.agent_cli.commands.agent_output import (
    CliOutputFormat,
    agent_error,
    agent_error_markdown,
    set_agent_cli_error_format,
)


class TestAgentErrorFormat:
    """Tests for agent_error dispatch and agent_error_markdown rendering."""

    def test_agent_error_defaults_to_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        """With no format opted in, agent_error keeps emitting JSON to stderr."""
        with pytest.raises(typer.Exit):
            agent_error("something went wrong", "FooError")
        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error"] is True
        assert parsed["error_type"] == "FooError"

    def test_agent_error_emits_markdown_when_format_is_markdown(self, capsys: pytest.CaptureFixture[str]) -> None:
        """When markdown is the active error format, agent_error renders markdown to stderr."""
        set_agent_cli_error_format(CliOutputFormat.MARKDOWN)
        with pytest.raises(typer.Exit) as exc_info:
            agent_error("something went wrong", "FooError")
        assert exc_info.value.exit_code == 1

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith("# Error: FooError")
        assert "something went wrong" in captured.err
        with pytest.raises(json.JSONDecodeError):
            json.loads(captured.err)

    def test_agent_error_markdown_renders_hint_and_details_but_omits_source(self, capsys: pytest.CaptureFixture[str]) -> None:
        """agent_error_markdown renders the heading, hint callout, and details — but not the source block.

        ``error_source`` (internal stack frames) is deliberately omitted from markdown — it's
        noise for an LLM trying to fix a `.mthds` file. The field still appears in the JSON
        envelope for programmatic consumers; that's covered by the integration test.
        """
        cause = ValueError("bad value")
        with pytest.raises(typer.Exit):
            agent_error_markdown(
                "model issue",
                "PipeOperatorModelChoiceError",
                cause=cause,
                pipe_code="my_pipe",
            )
        err = capsys.readouterr().err
        assert "# Error: PipeOperatorModelChoiceError" in err
        assert "model issue" in err
        assert "💡" in err  # hint callout for a known error type
        assert "**pipe_code:** my_pipe" in err
        assert "## Error source" not in err
        assert "error_source" not in err
