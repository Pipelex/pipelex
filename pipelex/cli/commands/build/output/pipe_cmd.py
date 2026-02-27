from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pipelex.cli.commands.build.output._output_core import execute_generate_output
from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat


def build_output_pipe_cmd(
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
        typer.Option("--output", "-o", help="Path to save the generated file (defaults to 'results/')"),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format: 'json' for JSON example, 'python' for Python code, 'schema' for JSON Schema (useful for TypeScript/Zod generation)",
        ),
    ] = "json",
) -> None:
    """Generate example output representation for a pipe by code.

    Examples:
        pipelex build output pipe my_domain.my_pipe
        pipelex build output pipe my_pipe --format schema
        pipelex build output pipe my_pipe -L ./my_library/
        pipelex build output pipe my_pipe --output expected_output.json
    """
    # Parse output format
    format_lower = output_format.lower()
    if format_lower == "json":
        concept_format = ConceptRepresentationFormat.JSON
    elif format_lower == "python":
        concept_format = ConceptRepresentationFormat.PYTHON
    elif format_lower == "schema":
        concept_format = ConceptRepresentationFormat.SCHEMA
    else:
        typer.secho(
            f"Invalid format '{output_format}'. Must be 'json', 'python', or 'schema'.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    output_path_path = Path(output_path) if output_path else None

    execute_generate_output(
        pipe_code=pipe_code,
        bundle_path=None,
        output_path=output_path_path,
        output_format=concept_format,
        library_dir=library_dir,
    )
