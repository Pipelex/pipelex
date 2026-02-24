"""Agent CLI mthds-list command — display the package manifest."""

from typing import Annotated

import typer

from pipelex.cli.agent_cli.commands.mthds_passthrough import run_mthds


def mthds_list_cmd(
    directory: Annotated[
        str | None,
        typer.Option("--directory", "-d", help="Package directory (defaults to current directory)"),
    ] = None,
) -> None:
    """Display the package manifest (METHODS.toml) for the current directory.

    This is a thin wrapper around ``mthds list`` that eliminates the need
    for agents to call the mthds binary directly.
    """
    args: list[str] = ["list"]
    if directory is not None:
        args.extend(["--directory", directory])
    run_mthds(args)
