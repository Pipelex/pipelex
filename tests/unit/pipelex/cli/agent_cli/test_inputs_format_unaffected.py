"""Regression test: the `inputs` commands' --format is the template serialization (json|toml), not the markdown|json pair."""

from __future__ import annotations

import inspect

from pipelex.cli.agent_cli.commands.inputs.bundle_cmd import inputs_bundle_cmd
from pipelex.cli.agent_cli.commands.inputs.method_cmd import inputs_method_cmd
from pipelex.cli.agent_cli.commands.inputs.pipe_cmd import inputs_pipe_cmd
from pipelex.pipe_machinery.rendering.input_renderer import InputsTemplateFormat


class TestInputsFormatUnaffected:
    """The `inputs` commands never gain the markdown|json presentation pair.

    Their `--format` is an InputsTemplateFormat (json|toml) selecting the template
    serialization — a deliberate deviation documented in the agent CLI CLAUDE.md.
    Errors stay on the ContextVar's JSON default: no --error-format.
    """

    def test_inputs_commands_have_template_format_not_presentation_format(self) -> None:
        """Each inputs subcommand declares template_format (InputsTemplateFormat) and no output_format/error_format."""
        for command in (inputs_pipe_cmd, inputs_bundle_cmd, inputs_method_cmd):
            parameters = inspect.signature(command).parameters
            assert "output_format" not in parameters, f"{command.__name__} unexpectedly gained an output_format parameter"
            assert "error_format" not in parameters, f"{command.__name__} unexpectedly gained an error_format parameter"
            template_format_param = parameters.get("template_format")
            assert template_format_param is not None, f"{command.__name__} lost its template_format parameter"
            assert template_format_param.default == InputsTemplateFormat.JSON, f"{command.__name__} must default to the JSON envelope"
