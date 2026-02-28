from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pipelex.builder.conventions import DEFAULT_BUNDLE_FILE_NAME
from pipelex.cli.commands.build.inputs._inputs_core import execute_generate_inputs
from pipelex.core.interpreter.helpers import MTHDS_EXTENSION, is_pipelex_file


def build_inputs_bundle_cmd(
    path: Annotated[
        str,
        typer.Argument(help="Path to a .mthds bundle file or a pipeline directory"),
    ],
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code (overrides bundle's main_pipe)"),
    ] = None,
    library_dir: Annotated[
        list[str] | None,
        typer.Option(
            "--library-dir",
            "-L",
            help="Directory to search for pipe definitions (.mthds files). Can be specified multiple times.",
        ),
    ] = None,
    output_path: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Path to save the generated JSON file (defaults to bundle's directory)"),
    ] = None,
) -> None:
    """Generate example input JSON from a bundle file or pipeline directory.

    Examples:
        pipelex build inputs bundle my_bundle.mthds
        pipelex build inputs bundle pipeline_01/
        pipelex build inputs bundle my_bundle.mthds --pipe my_pipe
        pipelex build inputs bundle pipeline_01/ --output custom_inputs.json
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
                    f"Pass the .mthds file directly, e.g.: pipelex build inputs bundle {target_path / mthds_files[0].name}",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(1)
            bundle_path = mthds_files[0]

        # Add directory as library dir
        target_dir_str = str(target_path)
        if library_dir is None:
            library_dir = [target_dir_str]
        elif target_dir_str not in library_dir:
            library_dir = [target_dir_str, *library_dir]

        typer.echo(f"Auto-detected bundle: {bundle_path}")

    elif is_pipelex_file(target_path):
        bundle_path = target_path
    else:
        typer.secho(
            f"Failed to run: '{path}' is not a .mthds file or directory.\n"
            f"  To generate inputs for a pipe by code, use: pipelex build inputs pipe <code>\n"
            f"  To use a bundle, pass a .mthds file or directory: pipelex build inputs bundle <path>",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    execute_generate_inputs(
        pipe_code=pipe,
        bundle_path=bundle_path,
        output_path=output_path_path,
        library_dir=library_dir,
    )
