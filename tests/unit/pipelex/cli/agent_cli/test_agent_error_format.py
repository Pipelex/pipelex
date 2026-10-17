from __future__ import annotations

import json

import pytest
import typer

from pipelex.cli.agent_cli.commands.agent_output import (
    CliOutputFormat,
    agent_error,
    set_agent_cli_error_format,
)
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError


class TestAgentErrorFormat:
    def test_agent_error_defaults_to_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        """With no format opted in, agent_error emits the problem as JSON on stderr."""
        with pytest.raises(typer.Exit):
            agent_error("something went wrong")
        parsed = json.loads(capsys.readouterr().err)
        assert parsed["code"] == "runtime.unexpected"
        assert parsed["message"] == "something went wrong"

    def test_agent_error_emits_markdown_when_format_is_markdown(self, capsys: pytest.CaptureFixture[str]) -> None:
        """When markdown is the active error format, agent_error renders the problem as Markdown on stderr."""
        set_agent_cli_error_format(CliOutputFormat.MARKDOWN)
        with pytest.raises(typer.Exit) as exc_info:
            agent_error("something went wrong")
        assert exc_info.value.exit_code == 1

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith("## ")
        assert "something went wrong" in captured.err
        assert "- Code: `runtime.unexpected` (domain runtime, retry no)" in captured.err
        with pytest.raises(json.JSONDecodeError):
            json.loads(captured.err)

    def test_markdown_renders_the_next_step_and_the_command_s_facts_but_no_source(self, capsys: pytest.CaptureFixture[str]) -> None:
        """The Markdown carries the next step, the code and the command's facts, never internal stack frames."""
        cause = PipeOperatorModelChoiceError(
            "model issue",
            pipe_type="PipeLLM",
            pipe_code="my_pipe",
            domain_code="my_domain",
            field_name="model",
            model_type=ModelType.LLM,
            model_choice="gpt-nope",
        )
        set_agent_cli_error_format(CliOutputFormat.MARKDOWN)
        with pytest.raises(typer.Exit):
            agent_error("model issue", cause=cause, pipe_code="my_pipe")
        err = capsys.readouterr().err
        problem_code = cause.resolve_error_code()
        assert f"- Code: `{problem_code}`" in err
        assert "**Next step** (`" in err
        assert "- **pipe_code:** my_pipe" in err
        assert "error_source" not in err
        assert "Traceback" not in err
