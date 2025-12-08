import asyncio
from pathlib import Path
from typing import Annotated

import click
import typer
from posthog import tag

from pipelex.builder.runner_code import generate_runner_code
from pipelex.cli.commands.build.app import build_app
from pipelex.cli.error_handlers import (
    ErrorContext,
    handle_model_availability_error,
    handle_model_choice_error,
    handle_model_deck_preset_error,
)
from pipelex.cogt.exceptions import ModelDeckPresetValidatonError
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.core.pipes.inputs.exceptions import PipeInputError
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.hub import get_required_pipe, get_telemetry_manager
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import PACKAGE_VERSION, Pipelex
from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventProperty
from pipelex.tools.misc.file_utils import (
    ensure_directory_for_file_path,
    get_incremental_file_path,
    save_text_to_path,
)

COMMAND = "build"
SUB_COMMAND_RUNNER = "runner"


@build_app.command(SUB_COMMAND_RUNNER, help="Build the Python code to run a pipe with the necessary inputs")
def prepare_runner_cmd(
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
            "--output", "-o", help="Path to save the generated Python file (defaults to bundle's directory if bundle provided, otherwise 'results/')"
        ),
    ] = None,
) -> None:
    """Prepare a Python runner file for a pipe.

    The generated file will include:
    - All necessary imports
    - Example input values based on the pipe's input types

    Native concept types (Text, Image, PDF, etc.) will be automatically handled.
    Custom concept types will have their structure recursively generated.

    Examples:
        pipelex build runner my_pipe
        pipelex build runner --bundle my_bundle.plx
        pipelex build runner --bundle my_bundle.plx --pipe my_pipe
        pipelex build runner my_bundle.plx
        pipelex build runner my_pipe --output runner.py
    """
    # Import here to avoid circular imports
    from pipelex.cli.commands.build.structures_cmd import generate_structures_from_blueprints  # noqa: PLC0415

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

    async def prepare_runner(pipe_code: str | None = None, bundle_path: str | None = None):
        bundle_blueprint = None
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

        # Determine if output is a list from the bundle blueprint
        output_is_list = False
        if bundle_blueprint and bundle_blueprint.pipe and pipe_code in bundle_blueprint.pipe:
            pipe_blueprint = bundle_blueprint.pipe[pipe_code]
            output_parse = parse_concept_with_multiplicity(pipe_blueprint.output)
            output_is_list = output_parse.multiplicity is not None

        # Determine output path - use bundle's directory if bundle provided, otherwise results/
        if output_path:
            final_output_path = output_path
        elif bundle_path:
            # Place runner in the same directory as the PLX file
            bundle_dir = Path(bundle_path).parent
            final_output_path = str(bundle_dir / f"run_{pipe_code}.py")
        else:
            final_output_path = get_incremental_file_path(
                base_path="results",
                base_name=f"run_{pipe_code}",
                extension="py",
            )
        output_dir = Path(final_output_path).parent

        # Generate structures folder FIRST (before runner, since runner imports from structures)
        if bundle_blueprint:
            structures_output_dir = output_dir / "structures"
            generated_structures = generate_structures_from_blueprints(
                blueprints=[bundle_blueprint],
                output_directory=structures_output_dir,
                target_path=output_dir,  # Check for existing structures in the bundle's directory
            )
            if generated_structures:
                typer.secho(f"✅ Generated {len(generated_structures)} structure(s) in: {structures_output_dir}", fg=typer.colors.GREEN)

        # Generate the runner code
        try:
            runner_code = generate_runner_code(the_pipe, output_multiplicity=output_is_list)
        except Exception as exc:
            typer.secho(f"❌ Error generating runner code: {exc}", fg=typer.colors.RED)
            raise typer.Exit(1) from exc

        # Save the runner file
        try:
            ensure_directory_for_file_path(file_path=final_output_path)
            save_text_to_path(text=runner_code, path=final_output_path)
            typer.secho(f"✅ Generated runner file: {final_output_path}", fg=typer.colors.GREEN)
        except Exception as exc:
            typer.secho(f"❌ Error saving file: {exc}", fg=typer.colors.RED)
            raise typer.Exit(1) from exc

    try:
        pipelex_instance = Pipelex.make(integration_mode=IntegrationMode.CLI)
    except ModelDeckPresetValidatonError as model_deck_error:
        handle_model_deck_preset_error(model_deck_error, context=ErrorContext.VALIDATION_BEFORE_BUILD_RUNNER)

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=PACKAGE_VERSION)
            tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} {SUB_COMMAND_RUNNER}")

            asyncio.run(prepare_runner(pipe_code=pipe_code, bundle_path=bundle_path))

    except PipeOperatorModelChoiceError as exc:
        handle_model_choice_error(exc, context=ErrorContext.BUILD)

    except PipeOperatorModelAvailabilityError as exc:
        handle_model_availability_error(exc, context=ErrorContext.BUILD)

    finally:
        pipelex_instance.teardown()
