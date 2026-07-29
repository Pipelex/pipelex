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
            help="Output format: 'json' for JSON example, 'python' for Python code, 'schema' for JSON Schema (useful for TypeScript/Zod generation)",
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

    pipe_code, method_library_dirs, _ = resolve_method_target(
        method_name=name,
        pipe_override=pipe,
        library_dirs=library_dir,
    )

    effective_library_dir = list(method_library_dirs)
    if library_dir:
        effective_library_dir.extend(library_dir)

    # Default output to a results/ folder inside the method's directory
    if output_path:
        output_path_path: Path | None = Path(output_path)
    else:
        results_dir = Path(method_library_dirs[0]) / "results"
        match concept_format:
            case ConceptRepresentationFormat.JSON:
                output_path_path = results_dir / "output.json"
            case ConceptRepresentationFormat.PYTHON:
                output_path_path = results_dir / "output.py"
            case ConceptRepresentationFormat.SCHEMA:
                output_path_path = results_dir / "output_schema.json"

    execute_generate_output(
        pipe_code=pipe_code,
        bundle_path=None,
        output_path=output_path_path,
        output_format=concept_format,
        library_dir=effective_library_dir,
    )
