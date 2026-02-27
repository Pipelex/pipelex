"""Agent CLI inputs subcommand group."""

from __future__ import annotations

import typer

from pipelex.cli.agent_cli.commands.inputs.bundle_cmd import inputs_bundle_cmd
from pipelex.cli.agent_cli.commands.inputs.method_cmd import inputs_method_cmd
from pipelex.cli.agent_cli.commands.inputs.pipe_cmd import inputs_pipe_cmd

inputs_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
)

inputs_app.command(name="method", help="Generate example inputs for an installed method")(inputs_method_cmd)
inputs_app.command(name="pipe", help="Generate example inputs for a pipe by code")(inputs_pipe_cmd)
inputs_app.command(name="bundle", help="Generate example inputs from a bundle file (.mthds) or directory")(inputs_bundle_cmd)
