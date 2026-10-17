from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pipelex.cli.commands.build.output._output_core import execute_generate_output
from pipelex.cli.commands.bundle_path_resolver import resolve_build_bundle_target
from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat

_NOT_A_BUNDLE_HINT = (
    "  To generate output for a pipe by code, use: pipelex build output pipe <code>\n"
    "  To use a bundle, pass a .mthds file or directory: pipelex build output bundle <path>"
)


def build_output_bundle_cmd(
    path: Annotated[
        str,
        typer.Argument(help="Path to a .mthds bundle file, or a method's folder, which starts at its entry pipe unless --pipe names one"),
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
        typer.Option("--output", "-o", help="Path to save the generated file (defaults to bundle's directory)"),
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
    """Generate example output representation from a bundle file or pipeline directory.

    Examples:
        pipelex build output bundle my_bundle.mthds
        pipelex build output bundle pipeline_01/
        pipelex build output bundle my_bundle.mthds --format schema
        pipelex build output bundle my_bundle.mthds --pipe my_pipe
        pipelex build output bundle pipeline_01/ --output expected_output.json
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
    # A folder is read as its method tree and acts on the pipe a run of it starts at, as `run bundle` reads it.
    target = resolve_build_bundle_target(path=path, library_dir=library_dir, pipe_override=pipe, not_a_bundle_hint=_NOT_A_BUNDLE_HINT)

    execute_generate_output(
        pipe_code=target.pipe_code,
        bundle_path=target.bundle_path,
        output_path=output_path_path,
        output_format=concept_format,
        default_output_dir=target.default_output_dir,
        library_dir=target.library_dir,
    )
