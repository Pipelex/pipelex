import asyncio
from pathlib import Path
from typing import Annotated

import click
import typer
from posthog import tag

from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.commands.build.app import build_app
from pipelex.cli.error_handlers import (
    ErrorContext,
    handle_model_availability_error,
    handle_model_choice_error,
)
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.core.pipes.inputs.exceptions import PipeInputError
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


@build_app.command(SUB_COMMAND_INPUTS, help="Generate example input JSON for a pipe")
def generate_inputs_cmd(
    target: Annotated[
        str | None,
        typer.Argument(help="Pipe code or bundle file path (auto-detected)"),
    ] = None,
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to use, can be omitted if you specify a bundle (.plx) that declares a main pipe"),
    ] = None,
    bundle: Annotated[
        str | None,
        typer.Option("--bundle", help="Bundle file path (.plx) - uses its main_pipe unless you specify a pipe code"),
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
        pipelex build inputs --bundle my_bundle.plx
        pipelex build inputs --bundle my_bundle.plx --pipe my_pipe
        pipelex build inputs my_bundle.plx
        pipelex build inputs my_pipe --output custom_inputs.json
    """
    # Validate mutual exclusivity
    provided_options = sum([target is not None, pipe is not None, bundle is not None])
    if provided_options == 0:
        ctx: click.Context = click.get_current_context()
        typer.echo(ctx.get_help())
        raise typer.Exit(0)

    # Let's analyze the options and determine what pipe code to use and if we need to load a bundle
    pipe_code: str | None = None
    bundle_path: str | None = None

    # Determine source:
    if target:
        # Check if target is a directory (not allowed for inputs command)
        target_path = Path(target)
        if target_path.is_dir():
            typer.secho(
                f"Failed to run: '{target}' is a directory. The inputs command requires a .plx file or a pipe code, not a directory.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(1)

        if target.endswith(".plx"):
            bundle_path = target
            if bundle:
                typer.secho(
                    "Failed to run: cannot use option --bundle if you're already passing a bundle file (.plx) as positional argument",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(1)
        else:
            pipe_code = target
            if pipe:
                typer.secho(
                    "Failed to run: cannot use option --pipe if you're already passing a pipe code as positional argument",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(1)

    if bundle:
        assert not bundle_path, "bundle_path should be None at this stage if --bundle is provided"
        bundle_path = bundle

    if pipe:
        assert not pipe_code, "pipe_code should be None at this stage if --pipe is provided"
        pipe_code = pipe

    if not pipe_code and not bundle_path:
        typer.secho("Failed to run: no pipe code or bundle file specified", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    async def generate_inputs(pipe_code: str | None = None, bundle_path: str | None = None):
        if bundle_path:
            try:
                validate_bundle_result = await validate_bundle(plx_file_path=bundle_path)
                bundle_blueprint = validate_bundle_result.blueprints[0]
                if not pipe_code:
                    main_pipe_code = bundle_blueprint.main_pipe
                    if not main_pipe_code:
                        # Fall back to first pipe if no main_pipe declared
                        if bundle_blueprint.pipe:
                            main_pipe_code = next(iter(bundle_blueprint.pipe.keys()))
                            typer.echo(f"No main_pipe declared, using first pipe '{main_pipe_code}' from bundle '{bundle_path}'")
                        else:
                            typer.secho(f"Bundle '{bundle_path}' has no pipes defined", fg=typer.colors.RED, err=True)
                            raise typer.Exit(1)
                    else:
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
            inputs_json_str = the_pipe.inputs.generate_json_string(indent=2)
        except Exception as exc:
            typer.secho(f"❌ Error generating input JSON: {exc}", fg=typer.colors.RED)
            raise typer.Exit(1) from exc

        # Determine output path - use bundle's directory if bundle provided, otherwise results/
        if output_path:
            final_output_path = output_path
        elif bundle_path:
            # Place inputs.json in the same directory as the PLX file
            bundle_dir = Path(bundle_path).parent
            final_output_path = str(bundle_dir / "inputs.json")
        else:
            final_output_path = "results/inputs.json"

        # Save the file
        try:
            ensure_directory_for_file_path(file_path=final_output_path)
            save_text_to_path(text=inputs_json_str, path=final_output_path)
            typer.secho(f"✅ Generated input JSON file: {final_output_path}", fg=typer.colors.GREEN)
        except Exception as exc:
            typer.secho(f"❌ Error saving file: {exc}", fg=typer.colors.RED)
            raise typer.Exit(1) from exc

    pipelex_instance = make_pipelex_for_cli(context=ErrorContext.VALIDATION_BEFORE_BUILD_INPUTS)

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=PACKAGE_VERSION)
            tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} {SUB_COMMAND_INPUTS}")

            asyncio.run(generate_inputs(pipe_code=pipe_code, bundle_path=bundle_path))

    except PipeOperatorModelChoiceError as exc:
        handle_model_choice_error(exc, context=ErrorContext.BUILD)

    except PipeOperatorModelAvailabilityError as exc:
        handle_model_availability_error(exc, context=ErrorContext.BUILD)

    finally:
        pipelex_instance.teardown()
