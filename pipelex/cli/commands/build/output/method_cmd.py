from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pipelex.cli.commands.build.output._output_core import execute_generate_output
from pipelex.cli.method_resolver import resolve_method_target
from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat


def build_output_method_cmd(
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
        typer.Option("--output", "-o", help="Path to save the generated file"),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format: 'json' for JSON example, 'python' for Python code, 'schema' for JSON Schema",
        ),
    ] = "json",
) -> None:
    """Generate example output representation for an installed method.

    Examples:
        pipelex build output method my-method
        pipelex build output method my-method --format schema
        pipelex build output method my-method --pipe custom_pipe
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

    pipe_code, method_library_dirs = resolve_method_target(
        method_name=name,
        pipe_override=pipe,
    )

    effective_library_dir = list(method_library_dirs)
    if library_dir:
        effective_library_dir.extend(library_dir)

    output_path_path = Path(output_path) if output_path else None

    execute_generate_output(
        pipe_code=pipe_code,
        bundle_path=None,
        output_path=output_path_path,
        output_format=concept_format,
        library_dir=effective_library_dir,
    )
