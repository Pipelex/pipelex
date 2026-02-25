"""Agent CLI run subcommand group."""

from __future__ import annotations

import typer

from pipelex.cli.agent_cli.commands.run.method_cmd import run_method_cmd
from pipelex.cli.agent_cli.commands.run.pipe_cmd import run_pipe_cmd

run_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
)

run_app.command(name="method", help="Execute a pipeline for an installed method")(run_method_cmd)
run_app.command(name="pipe", help="Execute a pipeline by pipe code or bundle path")(run_pipe_cmd)
