from __future__ import annotations

from pathlib import Path
from typing import Annotated

import click
import typer

from pipelex.cli.commands.build.output._output_core import execute_generate_output
from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.interpreter.helpers import is_pipelex_file


def build_output_pipe_cmd(
    target: Annotated[
        str | None,
        typer.Argument(help="Pipe code or bundle file path (auto-detected)"),
    ] = None,
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code, can be omitted if you specify a bundle (.mthds) that declares a main pipe"),
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
        typer.Option(
            "--output", "-o", help="Path to save the generated file (defaults to bundle's directory if bundle provided, otherwise 'results/')"
        ),
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
    """Generate example output representation for a pipe by code or bundle file.

    Examples:
        pipelex build output pipe my_pipe
        pipelex build output pipe my_pipe --format schema
        pipelex build output pipe my_bundle.mthds
        pipelex build output pipe my_bundle.mthds --pipe my_pipe
    """
    if target is None and pipe is None:
        ctx: click.Context = click.get_current_context()
        typer.echo(ctx.get_help())
        raise typer.Exit(0)

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

    pipe_code: str | None = None
    bundle_path: Path | None = None
    output_path_path = Path(output_path) if output_path else None

    if target:
        target_path = Path(target)
        if target_path.is_dir():
            typer.secho(
                f"Failed to run: '{target}' is a directory. The output command requires a .mthds file or a pipe code.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(1)

        if is_pipelex_file(target_path):
            bundle_path = target_path
        else:
            pipe_code = target
            if pipe:
                typer.secho(
                    "Failed to run: cannot use option --pipe if you're already passing a pipe code as positional argument",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(1)

    if pipe:
        assert not pipe_code, "pipe_code should be None at this stage if --pipe is provided"
        pipe_code = pipe

    if not pipe_code and not bundle_path:
        typer.secho("Failed to run: no pipe code or bundle file specified", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    execute_generate_output(
        pipe_code=pipe_code,
        bundle_path=bundle_path,
        output_path=output_path_path,
        output_format=concept_format,
        library_dir=library_dir,
    )
