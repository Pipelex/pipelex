from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from posthog import tag

from pipelex.builder.conventions import DEFAULT_INPUTS_FILE_NAME
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import (
    ErrorContext,
    handle_model_availability_error,
    handle_model_choice_error,
)
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.core.pipes.inputs.exceptions import PipeInputError
from pipelex.core.pipes.inputs.input_renderer import NoInputsRequiredError, render_inputs
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
SUB_COMMAND_INPUTS = "inputs"


async def _generate_inputs_core(
    pipe_code: str | None = None,
    bundle_path: Path | None = None,
    output_path: Path | None = None,
    library_dir: list[str] | None = None,
) -> None:
    """Core logic for generating input JSON for a pipe."""
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
                        f"Bundle '{bundle_path}' does not declare a main_pipe. In order to build inputs for a bundle, "
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
        typer.secho(f"Error: Could not find pipe '{pipe_code}': {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc

    try:
        inputs_json_str = render_inputs(the_pipe, indent=2)
    except NoInputsRequiredError as exc:
        typer.secho(str(exc), fg=typer.colors.YELLOW)
        raise typer.Exit(0) from exc
    except Exception as exc:
        typer.secho(f"Error generating input JSON: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc

    if output_path:
        final_output_path = output_path
    elif bundle_path:
        bundle_dir = bundle_path.parent
        final_output_path = bundle_dir / DEFAULT_INPUTS_FILE_NAME
    else:
        final_output_path = Path("results") / DEFAULT_INPUTS_FILE_NAME

    try:
        ensure_directory_for_file_path(file_path=str(final_output_path))
        save_text_to_path(text=inputs_json_str, path=str(final_output_path))
        typer.secho(f"Generated input JSON file: {final_output_path}", fg=typer.colors.GREEN)
    except Exception as exc:
        typer.secho(f"Error saving file: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc


def execute_generate_inputs(
    pipe_code: str | None,
    bundle_path: Path | None,
    output_path: Path | None,
    library_dir: list[str] | None = None,
    telemetry_command_label: str = f"{COMMAND} {SUB_COMMAND_INPUTS}",
) -> None:
    """Synchronous entry point wrapping the async inputs generation with Pipelex setup/teardown."""
    pipelex_instance = make_pipelex_for_cli(
        context=ErrorContext.VALIDATION_BEFORE_BUILD_INPUTS, library_dirs=library_dir, needs_inference=False, needs_model_specs=True
    )

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=PACKAGE_VERSION)
            tag(name=EventProperty.CLI_COMMAND, value=telemetry_command_label)

            asyncio.run(_generate_inputs_core(pipe_code=pipe_code, bundle_path=bundle_path, output_path=output_path, library_dir=library_dir))

    except PipeOperatorModelChoiceError as exc:
        handle_model_choice_error(exc, context=ErrorContext.BUILD)

    except PipeOperatorModelAvailabilityError as exc:
        handle_model_availability_error(exc, context=ErrorContext.BUILD)

    finally:
        pipelex_instance.teardown()
