import asyncio
from pathlib import Path
from typing import Annotated

import click
import typer
from posthog import tag

from pipelex.builder.conventions import DEFAULT_INPUTS_FILE_NAME
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import (
    ErrorContext,
    handle_model_availability_error,
    handle_model_choice_error,
)
from pipelex.core.interpreter.helpers import is_pipelex_file
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.core.pipes.inputs.exceptions import PipeInputError
from pipelex.core.pipes.inputs.input_renderer import NoInputsRequiredError, render_inputs
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
SUB_COMMAND_INPUTS = "inputs"


async def _generate_inputs_core(
    pipe_code: str | None = None,
    bundle_path: Path | None = None,
    output_path: Path | None = None,
) -> None:
    """Core logic for generating input JSON for a pipe.

    Args:
        pipe_code: The pipe code to generate inputs for.
        bundle_path: Path to the bundle file (.mthds).
        output_path: Path to save the generated JSON file.
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
                        f"Bundle '{bundle_path}' does not declare a main_pipe. In order to build inputs for a bundle, "
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
        typer.secho(f"❌ Error: Could not find pipe '{pipe_code}': {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc

    # Generate the input JSON
    try:
        inputs_json_str = render_inputs(the_pipe, indent=2)
    except NoInputsRequiredError as exc:
        typer.secho(str(exc), fg=typer.colors.YELLOW)
        raise typer.Exit(0) from exc
    except Exception as exc:
        typer.secho(f"❌ Error generating input JSON: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc

    # Determine output path - use bundle's directory if bundle provided, otherwise results/
    if output_path:
        final_output_path = output_path
    elif bundle_path:
        # Place inputs.json in the same directory as the MTHDS file
        bundle_dir = bundle_path.parent
        final_output_path = bundle_dir / DEFAULT_INPUTS_FILE_NAME
    else:
        final_output_path = Path("results") / DEFAULT_INPUTS_FILE_NAME

    # Save the file
    try:
        ensure_directory_for_file_path(file_path=str(final_output_path))
        save_text_to_path(text=inputs_json_str, path=str(final_output_path))
        typer.secho(f"✅ Generated input JSON file: {final_output_path}", fg=typer.colors.GREEN)
    except Exception as exc:
        typer.secho(f"❌ Error saving file: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc


def generate_inputs_cmd(
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
            "--output", "-o", help="Path to save the generated JSON file (defaults to bundle's directory if bundle provided, otherwise 'results/')"
        ),
    ] = None,
) -> None:
    """Generate example input JSON for a pipe.

    The generated JSON file will include example values for all pipe inputs
    based on their concept types.

    Examples:
        pipelex build inputs my_pipe
        pipelex build inputs my_bundle.mthds
        pipelex build inputs my_bundle.mthds --pipe my_pipe
        pipelex build inputs my_pipe --output custom_inputs.json
        pipelex build inputs my_pipe -L ./my_pipes
    """
    # Show help if nothing provided
    if target is None and pipe is None:
        ctx: click.Context = click.get_current_context()
        typer.echo(ctx.get_help())
        raise typer.Exit(0)

    # Determine pipe_code and bundle_path from target
    pipe_code: str | None = None
    bundle_path: Path | None = None
    output_path_path = Path(output_path) if output_path else None

    if target:
        target_path = Path(target)
        if target_path.is_dir():
            typer.secho(
                f"Failed to run: '{target}' is a directory. The inputs command requires a .mthds file or a pipe code.",
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

    pipelex_instance = make_pipelex_for_cli(context=ErrorContext.VALIDATION_BEFORE_BUILD_INPUTS, library_dirs=library_dir)

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=PACKAGE_VERSION)
            tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} {SUB_COMMAND_INPUTS}")

            asyncio.run(_generate_inputs_core(pipe_code=pipe_code, bundle_path=bundle_path, output_path=output_path_path))

    except PipeOperatorModelChoiceError as exc:
        handle_model_choice_error(exc, context=ErrorContext.BUILD)

    except PipeOperatorModelAvailabilityError as exc:
        handle_model_availability_error(exc, context=ErrorContext.BUILD)

    finally:
        pipelex_instance.teardown()
