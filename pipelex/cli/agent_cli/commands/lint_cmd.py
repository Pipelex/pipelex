"""Agent CLI lint command — lint a file using plxt."""

from typing import Annotated

import typer

from pipelex.cli.agent_cli.commands.plxt_passthrough import run_plxt


def lint_cmd(
    file_path: Annotated[
        str,
        typer.Argument(help="Path to the file to lint"),
    ],
) -> None:
    """Lint a .mthds, .toml, or .plx file using plxt.

    This is a thin wrapper around ``plxt lint`` that eliminates the need
    for agents to call the plxt binary directly.
    """
    run_plxt("lint", file_path)
