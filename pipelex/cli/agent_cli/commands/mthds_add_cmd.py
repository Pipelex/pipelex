"""Agent CLI mthds-add command — add a dependency to METHODS.toml."""

from typing import Annotated

import typer

from pipelex.cli.agent_cli.commands.mthds_passthrough import run_mthds


def mthds_add_cmd(
    address: Annotated[
        str,
        typer.Argument(help="Package address (e.g. 'github.com/org/repo')"),
    ],
    alias: Annotated[
        str | None,
        typer.Option("--alias", "-a", help="Dependency alias (auto-derived from address if not provided)"),
    ] = None,
    version: Annotated[
        str | None,
        typer.Option("--version", "-v", help="Version constraint"),
    ] = None,
    path: Annotated[
        str | None,
        typer.Option("--path", "-p", help="Local filesystem path to the dependency"),
    ] = None,
) -> None:
    """Add a dependency to METHODS.toml.

    This is a thin wrapper around ``mthds add`` that eliminates the need
    for agents to call the mthds binary directly.
    """
    args: list[str] = ["add", address]
    if alias is not None:
        args.extend(["--alias", alias])
    if version is not None:
        args.extend(["--version", version])
    if path is not None:
        args.extend(["--path", path])
    run_mthds(args)
