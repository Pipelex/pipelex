from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pipelex.builder.conventions import DEFAULT_BUNDLE_FILE_NAME
from pipelex.cli.commands.build.runner._runner_core import execute_prepare_runner
from pipelex.mthds_parsing.helpers import MTHDS_EXTENSION, is_pipelex_file


def build_runner_bundle_cmd(
    path: Annotated[
        str,
        typer.Argument(help="Path to a .mthds bundle file or a pipeline directory"),
    ],
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
    """Build a Python runner file from a bundle file or pipeline directory.

    Examples:
        pipelex build runner bundle my_bundle.mthds
        pipelex build runner bundle pipeline_01/
        pipelex build runner bundle my_bundle.mthds --pipe my_pipe
        pipelex build runner bundle my_bundle.mthds --output runner.py
    """
    target_path = Path(path)
    bundle_path: Path
    output_path_path = Path(output_path) if output_path else None

    if target_path.is_dir():
        bundle_file = target_path / DEFAULT_BUNDLE_FILE_NAME
        if bundle_file.is_file():
            bundle_path = bundle_file
        else:
            mthds_files = list(target_path.glob(f"*{MTHDS_EXTENSION}"))
            if len(mthds_files) == 0:
                typer.secho(
                    f"Failed to run: no .mthds bundle file found in directory '{path}'",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(1)
            if len(mthds_files) > 1:
                mthds_names = ", ".join(mthds_file.name for mthds_file in mthds_files)
                typer.secho(
                    f"Failed to run: multiple .mthds files found in '{path}' ({mthds_names}) "
                    f"and no '{DEFAULT_BUNDLE_FILE_NAME}'. "
                    f"Pass the .mthds file directly, e.g.: pipelex build runner bundle {target_path / mthds_files[0].name}",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(1)
            bundle_path = mthds_files[0]

        # Add directory as library dir
        target_dir_str = str(target_path)
        if library_dirs is None:
            library_dirs = [target_dir_str]
        elif target_dir_str not in library_dirs:
            library_dirs = [target_dir_str, *library_dirs]

        typer.echo(f"Auto-detected bundle: {bundle_path}")

    elif is_pipelex_file(target_path):
        bundle_path = target_path
    else:
        typer.secho(
            f"Failed to run: '{path}' is not a .mthds file or directory.\n"
            f"  To build a runner, pass a .mthds file or directory: pipelex build runner bundle <path>",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    library_dirs_paths = [Path(lib_dir) for lib_dir in library_dirs] if library_dirs else None

    execute_prepare_runner(
        pipe_code=pipe,
        bundle_path=bundle_path,
        output_path=output_path_path,
        library_dirs=library_dirs_paths,
    )
