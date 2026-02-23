"""Agent CLI mthds-publish command — publish package for distribution."""

from typing import Annotated

import typer

from pipelex.cli.agent_cli.commands.mthds_passthrough import run_mthds


def mthds_publish_cmd(
    tag: Annotated[
        bool,
        typer.Option("--tag", help="Create git tag v{version} locally on success"),
    ] = False,
) -> None:
    """Publish package for distribution.

    This is a thin wrapper around ``mthds publish`` that eliminates the need
    for agents to call the mthds binary directly.
    """
    args: list[str] = ["publish"]
    if tag:
        args.append("--tag")
    run_mthds(args)
