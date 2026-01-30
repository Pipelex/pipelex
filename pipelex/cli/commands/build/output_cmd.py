import asyncio
from pathlib import Path
from typing import Annotated

import click
import typer
from posthog import tag

from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import (
    ErrorContext,
    handle_model_availability_error,
    handle_model_choice_error,
)
from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.interpreter.helpers import is_pipelex_file
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.core.pipes.inputs.exceptions import PipeInputError
from pipelex.core.pipes.output.output_renderer import render_output
from pipelex.hub import get_required_pipe, get_telemetry_manager
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import PACKAGE_VERSION
from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventProperty
from pipelex.tools.misc.file_utils import (
    ensure_directory_for_file_path,
    save_text_to_path,
)

COMMAND = "build"
SUB_COMMAND_OUTPUT = "output"


async def _generate_output_core(
    pipe_code: str | None = None,
    bundle_path: Path | None = None,
    output_path: Path | None = None,
    output_format: ConceptRepresentationFormat = ConceptRepresentationFormat.JSON,
) -> None:
    """Core logic for generating output representation for a pipe.

    Args:
        pipe_code: The pipe code to generate output for.
        bundle_path: Path to the bundle file (.plx).
        output_path: Path to save the generated file.
        output_format: The format to generate (JSON, PYTHON, or SCHEMA).
    """
    if bundle_path:
        try:
            validate_bundle_result = await validate_bundle(plx_file_path=bundle_path)
            bundle_blueprint = validate_bundle_result.blueprints[0]
            if not pipe_code:
                # No pipe code specified, use main_pipe from bundle
                main_pipe_code = bundle_blueprint.main_pipe
                if not main_pipe_code:
                    msg = (
                        f"Bundle '{bundle_path}' does not declare a main_pipe. In order to build output for a bundle, "
                        "you must specify a main pipe in the bundle itself or specify a pipe code in the command line using the --pipe option."
                    )
                    typer.secho(
                        msg,
                        fg=typer.colors.RED,
                        err=True,
                    )
                    raise typer.Exit(1) from ValueError(msg)
                typer.echo(f"Using main pipe '{main_pipe_code}' from bundle '{bundle_path}'")
                pipe_code = main_pipe_code
            else:
                typer.echo(f"Using pipe '{pipe_code}' from bundle '{bundle_path}'")
        except FileNotFoundError as exc:
            typer.secho(f"Failed to load bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc
        except ValidateBundleError as exc:
            typer.secho(f"Failed to load bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc
        except PipeInputError as exc:
            typer.secho(f"Failed to load bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc
    elif not pipe_code:
        typer.secho("Failed to run: no pipe code specified", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    # Get the pipe
    try:
        the_pipe = get_required_pipe(pipe_code=pipe_code)
    except Exception as exc:
        typer.secho(f"Error: Could not find pipe '{pipe_code}': {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc

    # Generate the output representation
    try:
        output_str = render_output(the_pipe, output_format=output_format)
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.YELLOW)
        raise typer.Exit(0) from exc
    except Exception as exc:
        typer.secho(f"Error generating output: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc

    # Determine output path and file extension
    if output_path:
        final_output_path = output_path
    elif bundle_path:
        # Place output file in the same directory as the PLX file
        bundle_dir = Path(bundle_path).parent
        match output_format:
            case ConceptRepresentationFormat.JSON:
                final_output_path = bundle_dir / "output.json"
            case ConceptRepresentationFormat.PYTHON:
                final_output_path = bundle_dir / "output.py"
            case ConceptRepresentationFormat.SCHEMA:
                final_output_path = bundle_dir / "output_schema.json"
    else:
        match output_format:
            case ConceptRepresentationFormat.JSON:
                final_output_path = Path("results/output.json")
            case ConceptRepresentationFormat.PYTHON:
                final_output_path = Path("results/output.py")
            case ConceptRepresentationFormat.SCHEMA:
                final_output_path = Path("results/output_schema.json")

    # Save the file
    try:
        ensure_directory_for_file_path(file_path=str(final_output_path))
        save_text_to_path(text=output_str, path=str(final_output_path))
        typer.secho(f"Generated output file: {final_output_path}", fg=typer.colors.GREEN)
    except Exception as exc:
        typer.secho(f"Error saving file: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc


def generate_output_cmd(
    target: Annotated[
        str | None,
        typer.Argument(help="Pipe code or bundle file path (auto-detected)"),
    ] = None,
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code, can be omitted if you specify a bundle (.plx) that declares a main pipe"),
    ] = None,
    library_dir: Annotated[
        list[str] | None,
        typer.Option(
            "--library-dir",
            "-L",
            help="Directory to search for pipe definitions (.plx files). Can be specified multiple times.",
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
    """Generate example output representation for a pipe.

    The generated file will show the expected output structure
    based on the pipe's output concept type. For pipes with multiple
    possible outputs (e.g., PipeCondition), all options are included.

    Supported formats:

    - json: JSON object with example placeholder data (default)

    - python: Python class instantiation code

    - schema: JSON Schema definition, ideal for generating TypeScript
      interfaces or Zod schemas. Array outputs (e.g., MyType[5]) are
      represented as {"type": "array", "items": {...}}

    Examples:
        pipelex build output my_pipe

        pipelex build output my_pipe --format schema

        pipelex build output my_bundle.plx

        pipelex build output my_bundle.plx --pipe my_pipe

        pipelex build output my_pipe --output custom_output.json

        pipelex build output my_pipe -L ./my_pipes
    """
    # Show help if nothing provided
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

    # Determine pipe_code and bundle_path from target
    pipe_code: str | None = None
    bundle_path: Path | None = None
    output_path_path = Path(output_path) if output_path else None

    if target:
        target_path = Path(target)
        if target_path.is_dir():
            typer.secho(
                f"Failed to run: '{target}' is a directory. The output command requires a .plx file or a pipe code.",
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

    pipelex_instance = make_pipelex_for_cli(context=ErrorContext.VALIDATION_BEFORE_BUILD_OUTPUT, library_dirs=library_dir)

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=PACKAGE_VERSION)
            tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} {SUB_COMMAND_OUTPUT}")

            asyncio.run(
                _generate_output_core(pipe_code=pipe_code, bundle_path=bundle_path, output_path=output_path_path, output_format=concept_format)
            )

    except PipeOperatorModelChoiceError as exc:
        handle_model_choice_error(exc, context=ErrorContext.BUILD)

    except PipeOperatorModelAvailabilityError as exc:
        handle_model_availability_error(exc, context=ErrorContext.BUILD)

    finally:
        pipelex_instance.teardown()
