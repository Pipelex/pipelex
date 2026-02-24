"""Agent CLI mthds-validate command — validate METHODS.toml and optionally run deeper validation."""

from typing import Annotated

import typer

from pipelex.cli.agent_cli.commands.mthds_passthrough import run_mthds


def mthds_validate_cmd(
    target: Annotated[
        str | None,
        typer.Argument(help="Pipe code or .mthds file path (for runner validation)"),
    ] = None,
    all_pipes: Annotated[
        bool,
        typer.Option("--all", "-a", help="Validate all pipes via the runner"),
    ] = False,
    runner: Annotated[
        str | None,
        typer.Option("--runner", "-r", help="Runner for deeper validation (e.g. 'pipelex')"),
    ] = None,
    extra_args: Annotated[
        list[str] | None,
        typer.Argument(help="Additional arguments passed through to the runner"),
    ] = None,
    directory: Annotated[
        str | None,
        typer.Option("--directory", "-d", help="Package directory (defaults to current directory)"),
    ] = None,
) -> None:
    """Validate METHODS.toml and optionally run deeper validation via a runner.

    This is a thin wrapper around ``mthds validate`` that eliminates the need
    for agents to call the mthds binary directly.
    """
    args: list[str] = ["validate"]
    if target is not None:
        args.append(target)
    if all_pipes:
        args.append("--all")
    if runner is not None:
        args.extend(["--runner", runner])
    if extra_args:
        args.extend(extra_args)
    if directory is not None:
        args.extend(["--directory", directory])
    run_mthds(args)
