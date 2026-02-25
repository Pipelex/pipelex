from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pipelex.cli.commands.build.runner._runner_core import execute_prepare_runner
from pipelex.cli.installed_methods import find_method_by_name
from pipelex.cli.method_resolver import resolve_method_target


def build_runner_method_cmd(
    name: Annotated[
        str,
        typer.Argument(help="Name of the installed method"),
    ],
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code (overrides method's main_pipe)"),
    ] = None,
    output_path: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Path to save the generated Python file"),
    ] = None,
    library_dirs: Annotated[
        list[str] | None,
        typer.Option("--library-dirs", "-L", help="Directories to search for pipe definitions (.mthds files). Can be specified multiple times."),
    ] = None,
) -> None:
    """Build a Python runner file for an installed method.

    Resolves the method, finds a .mthds bundle in its directory,
    and generates a runner file.

    Examples:
        pipelex build runner method my-method
        pipelex build runner method my-method --pipe custom_pipe
        pipelex build runner method my-method --output runner.py
    """
    pipe_code, method_library_dirs = resolve_method_target(
        method_name=name,
        pipe_override=pipe,
    )

    # For runner generation, we need a bundle path. Use the first .mthds file from the method.
    method = find_method_by_name(name)
    if not method.mthds_files:
        typer.secho(
            f"Method '{name}' has no .mthds bundle files.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    bundle_path = method.mthds_files[0]
    # Default output to a results/ folder inside the method's directory
    if output_path:
        output_path_path: Path | None = Path(output_path)
    else:
        output_path_path = Path(method_library_dirs[0]) / "results" / f"run_{pipe_code}.py"

    library_dirs_paths = [Path(lib_dir) for lib_dir in method_library_dirs]
    if library_dirs:
        library_dirs_paths.extend(Path(lib_dir) for lib_dir in library_dirs)

    execute_prepare_runner(
        pipe_code=pipe_code,
        bundle_path=bundle_path,
        output_path=output_path_path,
        library_dirs=library_dirs_paths,
    )
