"""Agent CLI validate subcommand group."""

from __future__ import annotations

import typer

from pipelex.cli.agent_cli.commands.validate.bundle_cmd import validate_bundle_cmd
from pipelex.cli.agent_cli.commands.validate.method_cmd import validate_method_cmd
from pipelex.cli.agent_cli.commands.validate.pipe_cmd import validate_pipe_cmd

validate_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
)

validate_app.command(name="method", help="Validate an installed method")(validate_method_cmd)
validate_app.command(name="pipe", help="Validate a pipe by code, or all pipes")(validate_pipe_cmd)
validate_app.command(name="bundle", help="Validate a bundle file (.mthds) or pipeline directory")(validate_bundle_cmd)
