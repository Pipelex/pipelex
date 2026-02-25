"""Agent CLI fmt command — format a file using plxt."""

from typing import Annotated

import typer

from pipelex.cli.agent_cli.commands.plxt_passthrough import run_plxt


def fmt_cmd(
    file_path: Annotated[
        str,
        typer.Argument(help="Path to the file to format"),
    ],
) -> None:
    """Format a .mthds, .toml, or .plx file in-place using plxt.

    This is a thin wrapper around ``plxt fmt`` that eliminates the need
    for agents to call the plxt binary directly.
    """
    run_plxt("fmt", file_path)
