from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pipelex.cli.commands.build.runner._runner_core import execute_prepare_runner
from pipelex.cli.method_resolver import method_output_base_dir, resolve_method_target


def build_runner_method_cmd(
    name: Annotated[
        str,
        typer.Argument(help="Installed method name, method address (github.com/owner/repo[/name][@tag]), or GitHub URL"),
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
    pipe_code, method_library_dirs, method = resolve_method_target(
        method_name=name,
        pipe_override=pipe,
        library_dirs=library_dirs,
    )
    if not method.mthds_files:
        typer.secho(
            f"Method '{name}' has no .mthds bundle files.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    bundle_path = method.mthds_files[0]
    # Default output to a results/ folder under the method's output base (the caller's CWD for fetched methods)
    if output_path:
        output_path_path: Path | None = Path(output_path)
    else:
        output_path_path = method_output_base_dir(method=method) / "results" / f"run_{pipe_code}.py"

    library_dirs_paths = [Path(lib_dir) for lib_dir in method_library_dirs]
    if library_dirs:
        library_dirs_paths.extend(Path(lib_dir) for lib_dir in library_dirs)

    execute_prepare_runner(
        pipe_code=pipe_code,
        bundle_path=bundle_path,
        output_path=output_path_path,
        library_dirs=library_dirs_paths,
    )
