"""Regression test: the `inputs` command stays JSON-only (no --format / --error-format options)."""

from __future__ import annotations

import inspect

from pipelex.cli.agent_cli.commands.inputs.bundle_cmd import inputs_bundle_cmd
from pipelex.cli.agent_cli.commands.inputs.method_cmd import inputs_method_cmd
from pipelex.cli.agent_cli.commands.inputs.pipe_cmd import inputs_pipe_cmd


class TestInputsFormatUnaffected:
    """The `inputs` command always emits JSON — it must not gain --format or --error-format options."""

    def test_inputs_commands_have_no_format_params(self) -> None:
        """No inputs subcommand declares an output_format or error_format parameter."""
        for command in (inputs_pipe_cmd, inputs_bundle_cmd, inputs_method_cmd):
            parameters = inspect.signature(command).parameters
            assert "output_format" not in parameters, f"{command.__name__} unexpectedly gained an output_format parameter"
            assert "error_format" not in parameters, f"{command.__name__} unexpectedly gained an error_format parameter"
