from __future__ import annotations

from pathlib import Path
from typing import Annotated

import click
import typer

from pipelex.cli.commands.build.runner._runner_core import execute_prepare_runner
from pipelex.core.interpreter.helpers import is_pipelex_file


def build_runner_pipe_cmd(
    target: Annotated[
        str | None,
        typer.Argument(help="Bundle file path (.mthds)"),
    ] = None,
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to use (optional if the .mthds declares a main_pipe)"),
    ] = None,
    output_path: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Path to save the generated Python file (defaults to target's directory)"),
    ] = None,
    library_dirs: Annotated[
        list[str] | None,
        typer.Option("--library-dirs", "-L", help="Directories to search for pipe definitions (.mthds files). Can be specified multiple times."),
    ] = None,
) -> None:
    """Build a Python runner file for a pipe from a bundle file.

    Examples:
        pipelex build runner pipe my_bundle.mthds
        pipelex build runner pipe my_bundle.mthds --pipe my_pipe
        pipelex build runner pipe my_bundle.mthds --output runner.py
    """
    if target is None:
        ctx: click.Context = click.get_current_context()
        typer.echo(ctx.get_help())
        raise typer.Exit(0)

    target_path = Path(target)
    output_path_path = Path(output_path) if output_path else None
    library_dirs_paths = [Path(lib_dir) for lib_dir in library_dirs] if library_dirs else None

    if not is_pipelex_file(target_path):
        typer.secho(
            f"Failed to run: '{target}' is not a .mthds file.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    execute_prepare_runner(
        pipe_code=pipe,
        bundle_path=target_path,
        output_path=output_path_path,
        library_dirs=library_dirs_paths,
    )
