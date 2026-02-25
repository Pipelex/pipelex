from __future__ import annotations

from pathlib import Path
from typing import Annotated

import click
import typer

from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.commands.validate._validate_core import (
    COMMAND,
    do_validate_all_libraries_and_dry_run,
    execute_validate,
)
from pipelex.cli.error_handlers import ErrorContext
from pipelex.core.interpreter.helpers import is_pipelex_file
from pipelex.pipelex import Pipelex


def validate_pipe_cmd(
    target: Annotated[
        str | None,
        typer.Argument(help="Pipe code or bundle file path (auto-detected based on .mthds extension)"),
    ] = None,
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to validate (optional when using --bundle)"),
    ] = None,
    bundle: Annotated[
        str | None,
        typer.Option(
            "--bundle",
            help="Bundle file path (.mthds) - validates all pipes in the bundle",
        ),
    ] = None,
    validate_all: Annotated[
        bool,
        typer.Option("--all", "-a", help="Validate all pipes in all libraries"),
    ] = False,
    library_dir: Annotated[
        list[str] | None,
        typer.Option(
            "--library-dir",
            "-L",
            help="Directory to search for pipe definitions (.mthds files). Can be specified multiple times.",
        ),
    ] = None,
) -> None:
    """Validate and dry run a pipe or a bundle or all pipes.

    Examples:
        pipelex validate pipe my_pipe
        pipelex validate pipe my_bundle.mthds
        pipelex validate pipe --bundle my_bundle.mthds
        pipelex validate pipe --bundle my_bundle.mthds --pipe my_pipe
        pipelex validate pipe --all
    """
    if validate_all:
        if target or pipe or bundle:
            typer.secho(
                "Failed to validate: --all cannot be used with a target, --pipe, or --bundle",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(1)
        try:
            make_pipelex_for_cli(
                context=ErrorContext.VALIDATION,
                library_dirs=[Path(lib_dir) for lib_dir in library_dir] if library_dir else None,
            )
            do_validate_all_libraries_and_dry_run(library_dirs=[Path(lib_dir) for lib_dir in library_dir] if library_dir else None)
        finally:
            Pipelex.teardown_if_needed()
        return

    # Validate mutual exclusivity
    provided_options = sum([target is not None, pipe is not None, bundle is not None])
    if provided_options == 0:
        ctx: click.Context = click.get_current_context()
        typer.echo(ctx.get_help())
        raise typer.Exit(0)

    pipe_code: str | None = None
    bundle_path: Path | None = None
    library_dirs = [Path(lib_dir) for lib_dir in library_dir] if library_dir else None

    # Determine source
    if target:
        target_path = Path(target)
        if is_pipelex_file(target_path):
            bundle_path = target_path
            if bundle:
                typer.secho(
                    "Failed to validate: cannot use option --bundle if you're already passing a bundle file (.mthds) as positional argument",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(1)
        else:
            pipe_code = target
            if pipe:
                typer.secho(
                    "Failed to validate: cannot use option --pipe if you're already passing a pipe code as positional argument",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(1)

    if bundle:
        assert not bundle_path, "bundle_path should be None at this stage if --bundle is provided"
        bundle_path = Path(bundle)

    if pipe:
        assert not pipe_code, "pipe_code should be None at this stage if --pipe is provided"
        pipe_code = pipe

    if not pipe_code and not bundle_path:
        typer.secho(
            "Failed to validate: no pipe code or bundle file specified",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    execute_validate(
        pipe_code=pipe_code,
        bundle_path=bundle_path,
        library_dirs=library_dirs,
        telemetry_command_label=f"{COMMAND} pipe",
    )
