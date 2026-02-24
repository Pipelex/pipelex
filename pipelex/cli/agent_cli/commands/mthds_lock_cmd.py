"""Agent CLI mthds-lock command — resolve dependencies and generate methods.lock."""

from typing import Annotated

import typer

from pipelex.cli.agent_cli.commands.mthds_passthrough import run_mthds


def mthds_lock_cmd(
    directory: Annotated[
        str | None,
        typer.Option("--directory", "-d", help="Package directory (defaults to current directory)"),
    ] = None,
) -> None:
    """Resolve dependencies and generate methods.lock.

    This is a thin wrapper around ``mthds lock`` that eliminates the need
    for agents to call the mthds binary directly.
    """
    args: list[str] = ["lock"]
    if directory is not None:
        args.extend(["--directory", directory])
    run_mthds(args)
