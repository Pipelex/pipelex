"""Agent CLI mthds-update command — re-resolve dependencies and update methods.lock."""

from typing import Annotated

import typer

from pipelex.cli.agent_cli.commands.mthds_passthrough import run_mthds


def mthds_update_cmd(
    directory: Annotated[
        str | None,
        typer.Option("--directory", "-d", help="Package directory (defaults to current directory)"),
    ] = None,
) -> None:
    """Re-resolve dependencies and update methods.lock.

    This is a thin wrapper around ``mthds update`` that eliminates the need
    for agents to call the mthds binary directly.
    """
    args: list[str] = ["update"]
    if directory is not None:
        args.extend(["--directory", directory])
    run_mthds(args)
