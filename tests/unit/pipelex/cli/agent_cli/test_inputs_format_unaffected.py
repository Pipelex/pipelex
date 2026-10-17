from __future__ import annotations

import inspect
import json

import pytest
import typer

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, start_agent_cli_error_format
from pipelex.cli.agent_cli.commands.inputs.bundle_cmd import inputs_bundle_cmd
from pipelex.cli.agent_cli.commands.inputs.method_cmd import inputs_method_cmd
from pipelex.cli.agent_cli.commands.inputs.pipe_cmd import inputs_pipe_cmd
from pipelex.pipe_machinery.rendering.input_renderer import InputsTemplateFormat


class TestInputsFormatUnaffected:
    def test_inputs_commands_have_template_format_and_their_own_error_format(self) -> None:
        """Each inputs subcommand's --format is the template's (json|toml), never the markdown|json pair, and it takes --error-format.

        Its errors fall back on JSON, the template's default, unless --error-format, its own or the program's, says markdown.
        """
        for command in (inputs_pipe_cmd, inputs_bundle_cmd, inputs_method_cmd):
            parameters = inspect.signature(command).parameters
            assert "output_format" not in parameters, f"{command.__name__} unexpectedly gained an output_format parameter"
            template_format_param = parameters.get("template_format")
            assert template_format_param is not None, f"{command.__name__} lost its template_format parameter"
            assert template_format_param.default == InputsTemplateFormat.JSON, f"{command.__name__} must default to the JSON envelope"
            error_format_param = parameters.get("error_format")
            assert error_format_param is not None, f"{command.__name__} lost its error_format parameter"
            assert error_format_param.default is None, f"{command.__name__} must inherit the program's error format"

    @pytest.mark.parametrize(
        ("root_error_format", "command_error_format", "is_markdown"),
        [
            (None, None, False),
            (CliOutputFormat.MARKDOWN, None, True),
            (None, CliOutputFormat.MARKDOWN, True),
            (CliOutputFormat.MARKDOWN, CliOutputFormat.JSON, False),
        ],
    )
    def test_an_inputs_refusal_follows_the_error_format(
        self,
        capsys: pytest.CaptureFixture[str],
        root_error_format: CliOutputFormat | None,
        command_error_format: CliOutputFormat | None,
        is_markdown: bool,
    ) -> None:
        start_agent_cli_error_format(root_error_format=root_error_format)
        with pytest.raises(typer.Exit) as exc_info:
            inputs_pipe_cmd(pipe_code="my_pipe.mthds", error_format=command_error_format)
        assert exc_info.value.exit_code == 1

        err = capsys.readouterr().err
        if is_markdown:
            assert err.startswith("## An argument was refused before sending")
        else:
            parsed = json.loads(err)
            assert parsed["code"] == "client.argument_invalid"
            assert parsed["params"] == {"argument": "my_pipe.mthds", "reason": "a path where a pipe code is expected"}
