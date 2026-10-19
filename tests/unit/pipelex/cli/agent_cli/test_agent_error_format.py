from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
import typer
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError, ValidationErrorCategory, ValidationErrorItem
from pipelex.cli.agent_cli.commands.agent_output import (
    CliOutputFormat,
    agent_error,
    set_agent_cli_error_format,
)
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.errors.problem import make_problem_item
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.validation_error_types import PipeValidationErrorType

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


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

    @pytest.mark.parametrize("error_format", [CliOutputFormat.JSON, CliOutputFormat.MARKDOWN])
    @pytest.mark.builds_problems_without_required_params(
        reason="builds its verdict's items in the test, without an unresolved pipe's candidates or a residual's field path"
    )
    def test_both_formats_list_the_one_problem_s_errors(self, capsys: pytest.CaptureFixture[str], error_format: CliOutputFormat) -> None:
        """A wrapper adding a fault of its own above a verdict: both formats list the verdict's item and the wrapper's."""
        set_agent_cli_error_format(error_format)
        verdict = ValidateBundleError(message="the verdict's own fault")
        wrapper = PipelexError("several faults")
        wrapper.with_items(items=[make_problem_item(code=CoreCode.METHOD_PIPE_UNRESOLVED, params={"pipe": "summarize", "missing": "condense"})])
        wrapper.__cause__ = verdict

        with pytest.raises(typer.Exit):
            agent_error("the run was refused", cause=wrapper)

        printed = capsys.readouterr().err
        missing_pipe = "Pipe 'summarize' names the pipe 'condense', which does not exist."
        match error_format:
            case CliOutputFormat.JSON:
                problem = json.loads(printed)
                assert [item["code"] for item in problem["errors"]] == ["method.schema_violation", "method.pipe_unresolved"]
                assert problem["errors"][1]["detail"] == missing_pipe
            case CliOutputFormat.MARKDOWN:
                assert "### Errors" in printed
                assert f"- `method.pipe_unresolved`: {missing_pipe}" in printed
                assert "- `method.schema_violation`: " in printed

    @pytest.mark.parametrize("error_format", [CliOutputFormat.JSON, CliOutputFormat.MARKDOWN])
    def test_an_invalid_verdict_lists_its_problem_items_in_both_formats(
        self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str], error_format: CliOutputFormat
    ) -> None:
        """An invalid bundle's Markdown lists the problem's items, code, detail, location and suggestions, as its JSON does."""
        set_agent_cli_error_format(error_format)
        item = ValidationErrorItem(
            category=ValidationErrorCategory.PIPE_VALIDATION,
            error_type=PipeValidationErrorType.UNKNOWN_MODEL,
            message="Pipe 'draft_pitch' (PipeLLM), field 'model': Model handle 'gpt-5.1' was not found in the model deck",
            pipe_code="draft_pitch",
            domain_code="sales_copy",
            field_name="model",
            model_reference="gpt-5.1",
            model_type="llm",
            suggestions=["gpt-5.5", "gpt-5.4"],
            source="pitch.mthds",
        )
        verdict = ValidateBundleError(message="the bundle does not validate")
        mocker.patch.object(verdict, "validation_error_items", return_value=[item])

        with pytest.raises(typer.Exit):
            agent_error("the bundle does not validate", cause=verdict)

        printed = capsys.readouterr().err
        match error_format:
            case CliOutputFormat.JSON:
                problem = json.loads(printed)
                assert problem["errors"] == [
                    {
                        "code": "model.unknown",
                        "detail": "The method names the llm model 'gpt-5.1', which no catalog knows.",
                        "params": {"model": "gpt-5.1", "model_type": "llm", "suggestions": ["gpt-5.5", "gpt-5.4"]},
                        "location": {"pipe": "draft_pitch", "field": "model", "file": "pitch.mthds"},
                        "suggestions": ["gpt-5.5", "gpt-5.4"],
                    }
                ]
            case CliOutputFormat.MARKDOWN:
                assert (
                    "### Errors\n\n"
                    "- `model.unknown`: The method names the llm model 'gpt-5.1', which no catalog knows. "
                    "(pipe 'draft_pitch', field 'model', file 'pitch.mthds')\n"
                    "  - Suggestions: `gpt-5.5`, `gpt-5.4`"
                ) in printed
                for retired_prose in ("## Pipe validation errors", "Domain:", "Declared concepts", "Source:"):
                    assert retired_prose not in printed
