from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pipelex.cli.commands.build.inputs._inputs_core import execute_generate_inputs


def build_inputs_pipe_cmd(
    pipe_code: Annotated[
        str,
        typer.Argument(help="Pipe code (e.g. my_domain.my_pipe)"),
    ],
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
        typer.Option("--output", "-o", help="Path to save the generated JSON file (defaults to 'results/')"),
    ] = None,
) -> None:
    """Generate example input JSON for a pipe by code.

    Examples:
        pipelex build inputs pipe my_domain.my_pipe
        pipelex build inputs pipe my_pipe -L ./my_library/
        pipelex build inputs pipe my_pipe --output custom_inputs.json
    """
    output_path_path = Path(output_path) if output_path else None

    execute_generate_inputs(
        pipe_code=pipe_code,
        bundle_path=None,
        output_path=output_path_path,
        library_dir=library_dir,
    )
