from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pipelex.cli.commands.build.inputs._inputs_core import execute_generate_inputs
from pipelex.cli.method_resolver import resolve_method_target


def build_inputs_method_cmd(
    name: Annotated[
        str,
        typer.Argument(help="Name of the installed method"),
    ],
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code (overrides method's main_pipe)"),
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
        typer.Option("--output", "-o", help="Path to save the generated JSON file"),
    ] = None,
) -> None:
    """Generate example input JSON for an installed method.

    Examples:
        pipelex build inputs method my-method
        pipelex build inputs method my-method --pipe custom_pipe
        pipelex build inputs method my-method --output custom_inputs.json
    """
    pipe_code, method_library_dirs = resolve_method_target(
        method_name=name,
        pipe_override=pipe,
    )

    effective_library_dir = list(method_library_dirs)
    if library_dir:
        effective_library_dir.extend(library_dir)

    output_path_path = Path(output_path) if output_path else None

    execute_generate_inputs(
        pipe_code=pipe_code,
        bundle_path=None,
        output_path=output_path_path,
        library_dir=effective_library_dir,
    )
