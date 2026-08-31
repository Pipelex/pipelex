from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated

import typer

from pipelex.cli.commands.build.runner._runner_core import execute_prepare_runner
from pipelex.cli.method_resolver import method_output_base_dir, resolve_method_target


def build_runner_method_cmd(
    name: Annotated[
        str,
        typer.Argument(help="Installed method name, method address (github.com/owner/repo\\[/name]\\[@tag]), or GitHub URL"),
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
    output_path_path: Path
    if output_path:
        output_path_path = Path(output_path)
    else:
        output_path_path = method_output_base_dir(method=method) / "results" / f"run_{pipe_code}.py"

    if method.provenance is not None:
        # The generated script embeds the library dir it loads at run time, and a fetched
        # package's directory is an ephemeral clone deleted at process exit — so a runner
        # pointing there would be broken on first use. Materialize the package beside the
        # generated script and embed that path instead, keeping the artifact self-contained.
        materialized_dir = output_path_path.parent / method.name
        shutil.copytree(method.path, materialized_dir, ignore=shutil.ignore_patterns(".git", "__pycache__"), dirs_exist_ok=True)
        bundle_path = materialized_dir / bundle_path.relative_to(method.path)
        method_library_dirs = [str(materialized_dir)]
        typer.secho(f"Copied fetched package into {materialized_dir} (referenced by the generated runner)", fg=typer.colors.BLUE, err=True)

    library_dirs_paths = [Path(lib_dir) for lib_dir in method_library_dirs]
    if library_dirs:
        library_dirs_paths.extend(Path(lib_dir) for lib_dir in library_dirs)

    execute_prepare_runner(
        pipe_code=pipe_code,
        bundle_path=bundle_path,
        output_path=output_path_path,
        library_dirs=library_dirs_paths,
    )
