from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.commands.validate._validate_core import (
    COMMAND,
    do_validate_all_libraries_and_dry_run,
    execute_validate,
)
from pipelex.cli.error_handlers import ErrorContext
from pipelex.cli.method_resolver import resolve_pipe_from_exports
from pipelex.core.interpreter.helpers import MTHDS_EXTENSION, is_pipelex_file
from pipelex.pipelex import Pipelex


def validate_pipe_cmd(
    pipe_code: Annotated[
        str | None,
        typer.Argument(help="Pipe code to validate"),
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
    allow_signatures: Annotated[
        bool,
        typer.Option(
            "--allow-signatures",
            help="Accept PipeSignature placeholders in the dependency graph (lenient mode).",
        ),
    ] = False,
) -> None:
    """Validate and dry run a pipe by code, or all pipes.

    Examples:
        pipelex validate pipe my_pipe
        pipelex validate pipe --all
        pipelex validate pipe my_pipe -L ./my_pipes
        pipelex validate pipe --all --allow-signatures
    """
    if validate_all:
        if pipe_code:
            typer.secho(
                "Failed to validate: --all cannot be used with a pipe code",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(1)
        library_dirs_paths = [Path(lib_dir) for lib_dir in library_dir] if library_dir else None
        try:
            make_pipelex_for_cli(
                context=ErrorContext.VALIDATION,
                library_dirs=library_dirs_paths,
                needs_inference=False,
                needs_model_specs=True,
            )
            do_validate_all_libraries_and_dry_run(
                library_dirs=library_dirs_paths,
                allow_signatures=allow_signatures,
            )
        finally:
            Pipelex.teardown_if_needed()
        return

    if not pipe_code:
        typer.secho(
            "Failed to validate: no pipe code specified. Use --all to validate all pipes,\n"
            "or use 'pipelex validate bundle <path>' to validate a bundle file.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    # Helpful error if the user passes a path instead of a pipe code
    target_path = Path(pipe_code)
    if target_path.is_dir() or is_pipelex_file(target_path) or pipe_code.endswith(MTHDS_EXTENSION):
        typer.secho(
            f"Failed to validate: '{pipe_code}' looks like a file path or directory.\n"
            f"  To validate a bundle or directory, use: pipelex validate bundle {pipe_code}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    # Check installed methods' exports for additional library dirs
    try:
        extra_dirs = resolve_pipe_from_exports(pipe_code)
    except ValueError as exc:
        typer.secho(
            f"Ambiguous pipe code '{pipe_code}': {exc}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1) from exc
    if extra_dirs:
        if library_dir is None:
            library_dir = extra_dirs
        else:
            library_dir = [*extra_dirs, *library_dir]

    library_dirs_paths = [Path(lib_dir) for lib_dir in library_dir] if library_dir else None

    execute_validate(
        pipe_code=pipe_code,
        bundle_path=None,
        library_dirs=library_dirs_paths,
        telemetry_command_label=f"{COMMAND} pipe",
        allow_signatures=allow_signatures,
    )
