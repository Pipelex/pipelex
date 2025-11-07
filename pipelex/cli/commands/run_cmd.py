from __future__ import annotations

import asyncio
import json
from typing import Annotated

import click
import typer
from posthog import tag
from rich.console import Console

from pipelex import log, pretty_print_md
from pipelex.builder.builder import load_and_validate_bundle
from pipelex.builder.builder_errors import PipelexBundleError
from pipelex.cli.error_handlers import (
    ErrorContext,
    handle_model_availability_error,
    handle_model_choice_error,
    handle_model_deck_preset_error,
    handle_validation_error,
)
from pipelex.cogt.exceptions import ModelDeckPresetValidatonError
from pipelex.exceptions import (
    LibraryLoadingError,
    PipeInputError,
    PipelineExecutionError,
    PipeOperatorModelAvailabilityError,
    PipeOperatorModelChoiceError,
)
from pipelex.hub import get_telemetry_manager
from pipelex.pipelex import Pipelex
from pipelex.pipeline.execute import execute_pipeline
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventProperty
from pipelex.tools.misc.file_utils import get_incremental_file_path
from pipelex.tools.misc.json_utils import JsonTypeError, load_json_dict_from_path, save_as_json_to_path
from pipelex.tools.misc.package_utils import get_package_version

COMMAND = "run"


def run_cmd(
    target: Annotated[
        str | None,
        typer.Argument(help="Pipe code or bundle file path (auto-detected)"),
    ] = None,
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to run, can be omitted if you specify a bundle (.plx) that declares a main pipe"),
    ] = None,
    bundle: Annotated[
        str | None,
        typer.Option("--bundle", help="Bundle file path (.plx) - runs its main_pipe unless you specify a pipe code"),
    ] = None,
    inputs: Annotated[
        str | None,
        typer.Option("--inputs", "-i", help="Path to JSON file with inputs"),
    ] = None,
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Path to save output JSON, default to '{pipe_code}.json'"),
    ] = None,
    no_output: Annotated[
        bool,
        typer.Option("--no-output", help="Skip saving output to file"),
    ] = False,
    no_pretty_print: Annotated[
        bool,
        typer.Option("--no-pretty-print", help="Skip pretty printing the main_stuff"),
    ] = False,
) -> None:
    """Execute a pipeline from a specific bundle file (or not), specifying its pipe code or not.
    If the bundle is provided, it will run its main pipe unless you specify a pipe code.
    If the pipe code is provided, you don't need to provide a bundle file if it's already part of the imported packages.

    Examples:
        pipelex run my_pipe
        pipelex run --bundle my_bundle.plx
        pipelex run --bundle my_bundle.plx --pipe my_pipe
        pipelex run --pipe my_pipe --inputs data.json
        pipelex run my_bundle.plx --inputs data.json
        pipelex run my_pipe --output results.json --no-pretty-print
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

    async def run_pipeline(pipe_code: str | None = None, bundle_path: str | None = None):
        source_description: str
        if bundle_path:
            try:
                bundle_blueprint = await load_and_validate_bundle(bundle_path)
                if not pipe_code:
                    main_pipe_code = bundle_blueprint.main_pipe
                    if not main_pipe_code:
                        typer.secho(f"Bundle '{bundle_path}' does not declare a main_pipe", fg=typer.colors.RED, err=True)
                        raise typer.Exit(1)
                    pipe_code = main_pipe_code
                    source_description = f"bundle '{bundle_path}' • main pipe: '{pipe_code}'"
                else:
                    source_description = f"bundle '{bundle_path}' • pipe: '{pipe_code}'"
            except FileNotFoundError as exc:
                typer.secho(f"Failed to load bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from exc
            except PipelexBundleError as exc:
                typer.secho(f"Failed to load bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from exc
            except PipeInputError as exc:
                typer.secho(f"Failed to load bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from exc
        elif pipe_code:
            source_description = f"pipe '{pipe_code}'"
        else:
            typer.secho("Failed to run: no pipe code specified", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)

        # Load inputs if provided
        pipeline_inputs = None
        if inputs:
            if inputs.startswith("{"):
                pipeline_inputs = json.loads(inputs)
            else:
                try:
                    pipeline_inputs = load_json_dict_from_path(inputs)
                    typer.echo(f"Loaded inputs from: {inputs}")
                except FileNotFoundError as file_not_found_exc:
                    typer.secho(f"Failed to load input file '{inputs}': file not found", fg=typer.colors.RED, err=True)
                    raise typer.Exit(1) from file_not_found_exc
                except JsonTypeError as json_type_error_exc:
                    typer.secho(f"Failed to parse input file '{inputs}': must be a valid JSON dictionary", fg=typer.colors.RED, err=True)
                    raise typer.Exit(1) from json_type_error_exc

        # Execute pipeline
        typer.secho(f"\n🚀 Executing {source_description}...\n", fg=typer.colors.GREEN, bold=True)

        try:
            pipe_output = await execute_pipeline(
                pipe_code=pipe_code,
                inputs=pipeline_inputs,
            )
        except PipelineExecutionError as exc:
            typer.secho(f"Failed to execute pipeline: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc

        # Pretty print main_stuff unless disabled
        if not no_pretty_print:
            typer.echo("")
            pretty_print_md(content=pipe_output.main_stuff.content.rendered_markdown(), title=f"Main output of '{pipe_code}'")
            typer.echo("")

        # Save working memory to JSON unless disabled
        if not no_output:
            output_path = output or get_incremental_file_path(
                base_path="results",
                base_name=f"run_{pipe_code}",
                extension="json",
            )
            working_memory_dict = pipe_output.working_memory.smart_dump()
            save_as_json_to_path(object_to_save=working_memory_dict, path=output_path)
            typer.secho(f"✅ Working memory saved to: {output_path}", fg=typer.colors.GREEN)

        typer.secho("✅ Pipeline execution completed successfully", fg=typer.colors.GREEN)

    # Initialize Pipelex BEFORE telemetry context to ensure proper setup
    try:
        pipelex_instance = Pipelex.make(integration_mode=IntegrationMode.CLI)
    except LibraryLoadingError as library_loading_error:
        handle_validation_error(exc=library_loading_error, context=ErrorContext.VALIDATION_BEFORE_PIPE_RUN)
    except ModelDeckPresetValidatonError as model_deck_error:
        handle_model_deck_preset_error(model_deck_error, context=ErrorContext.VALIDATION_BEFORE_PIPE_RUN)

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
            tag(name=EventProperty.CLI_COMMAND, value=COMMAND)
            asyncio.run(run_pipeline(pipe_code=pipe_code, bundle_path=bundle_path))

    except PipeOperatorModelChoiceError as exc:
        handle_model_choice_error(exc, context=ErrorContext.PIPE_RUN)

    except PipeOperatorModelAvailabilityError as exc:
        handle_model_availability_error(exc, context=ErrorContext.PIPE_RUN)

    except Exception as exc:
        log.error(f"Error executing pipeline: {exc}")
        console = Console(stderr=True)
        console.print("\n[bold red]Failed to execute pipeline[/bold red]\n")
        console.print_exception(show_locals=True)
        raise typer.Exit(1) from exc
    finally:
        pipelex_instance.teardown()
