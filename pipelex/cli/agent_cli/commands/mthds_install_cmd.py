"""Agent CLI mthds-install command — install dependencies from methods.lock."""

from typing import Annotated

import typer

from pipelex.cli.agent_cli.commands.mthds_passthrough import run_mthds


def mthds_install_cmd(
    directory: Annotated[
        str | None,
        typer.Option("--directory", "-d", help="Package directory (defaults to current directory)"),
    ] = None,
) -> None:
    """Install dependencies from methods.lock.

    This is a thin wrapper around ``mthds install`` that eliminates the need
    for agents to call the mthds binary directly.
    """
    args: list[str] = ["install"]
    if directory is not None:
        args.extend(["--directory", directory])
    run_mthds(args)
