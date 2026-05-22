from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from posthog import tag

from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import (
    ErrorContext,
    handle_model_availability_error,
    handle_model_choice_error,
)
from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.core.pipes.inputs.exceptions import PipeInputError
from pipelex.core.pipes.output.output_renderer import render_output
from pipelex.hub import get_library_manager, get_required_pipe, get_telemetry_manager, resolve_library_dirs, set_current_library
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
    library_dir: list[str] | None = None,
) -> None:
    """Core logic for generating output representation for a pipe."""
    # Set up library so pipes can be found
    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    set_current_library(library_id=library_id)
    effective_dirs, _ = resolve_library_dirs(library_dir)
    if effective_dirs:
        library_manager.load_libraries(library_id=library_id, library_dirs=effective_dirs)

    if bundle_path:
        try:
            validate_bundle_result = await validate_bundle(mthds_file_path=bundle_path)
            bundle_blueprint = validate_bundle_result.blueprints[0]
            if not pipe_code:
                main_pipe_code = bundle_blueprint.main_pipe
                if not main_pipe_code:
                    msg = (
                        f"Bundle '{bundle_path}' does not declare a main_pipe. In order to build output for a bundle, "
                        "you must specify a main pipe in the bundle itself or specify a pipe code in the command line using the --pipe option."
                    )
                    typer.secho(msg, fg=typer.colors.RED, err=True)
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

    try:
        the_pipe = get_required_pipe(pipe_code=pipe_code)
    except Exception as exc:
        # CLI command boundary: any failure resolving the pipe is reported to the user and exits via typer.Exit.
        typer.secho(f"Error: Could not find pipe '{pipe_code}': {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc

    try:
        output_str = render_output(the_pipe, output_format=output_format)
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.YELLOW)
        raise typer.Exit(0) from exc
    except Exception as exc:
        # CLI command boundary: any failure generating the output is reported to the user and exits via typer.Exit.
        typer.secho(f"Error generating output: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc

    final_output_path: Path
    if output_path:
        final_output_path = output_path
    elif bundle_path:
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

    try:
        ensure_directory_for_file_path(file_path=str(final_output_path))
        save_text_to_path(text=output_str, path=str(final_output_path))
        typer.secho(f"Generated output file: {final_output_path}", fg=typer.colors.GREEN)
    except Exception as exc:
        # CLI command boundary: any failure writing the file is reported to the user and exits via typer.Exit.
        typer.secho(f"Error saving file: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc


def execute_generate_output(
    pipe_code: str | None,
    bundle_path: Path | None,
    output_path: Path | None,
    output_format: ConceptRepresentationFormat,
    library_dir: list[str] | None = None,
    telemetry_command_label: str = f"{COMMAND} {SUB_COMMAND_OUTPUT}",
) -> None:
    """Synchronous entry point wrapping the async output generation with Pipelex setup/teardown."""
    pipelex_instance = make_pipelex_for_cli(
        context=ErrorContext.VALIDATION_BEFORE_BUILD_OUTPUT, library_dirs=library_dir, needs_inference=False, needs_model_specs=True
    )

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=PACKAGE_VERSION)
            tag(name=EventProperty.CLI_COMMAND, value=telemetry_command_label)

            asyncio.run(
                _generate_output_core(
                    pipe_code=pipe_code, bundle_path=bundle_path, output_path=output_path, output_format=output_format, library_dir=library_dir
                )
            )

    except PipeOperatorModelChoiceError as exc:
        handle_model_choice_error(exc, context=ErrorContext.BUILD)

    except PipeOperatorModelAvailabilityError as exc:
        handle_model_availability_error(exc, context=ErrorContext.BUILD)

    finally:
        pipelex_instance.teardown()
