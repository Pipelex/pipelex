"""Agent CLI mthds-init command — initialize a METHODS.toml package manifest."""

from typing import Annotated

import typer

from pipelex.cli.agent_cli.commands.mthds_passthrough import run_mthds


def mthds_init_cmd(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Overwrite existing METHODS.toml"),
    ] = False,
) -> None:
    """Initialize a METHODS.toml package manifest in the current directory.

    This is a thin wrapper around ``mthds init`` that eliminates the need
    for agents to call the mthds binary directly.
    """
    args: list[str] = ["init"]
    if force:
        args.append("--force")
    run_mthds(args)
