import asyncio
import time
from typing import TYPE_CHECKING, Annotated

import click
import typer
from posthog import tag

from pipelex import pretty_print
from pipelex.builder.builder import PipelexBundleSpec, load_and_validate_bundle
from pipelex.builder.builder_errors import PipeBuilderError, PipelexBundleError
from pipelex.builder.builder_loop import BuilderLoop
from pipelex.builder.runner_code import generate_input_memory_json_string, generate_runner_code
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
from pipelex.hub import get_report_delegate, get_required_pipe, get_telemetry_manager
from pipelex.language.plx_factory import PlxFactory
from pipelex.pipelex import PACKAGE_VERSION, Pipelex
from pipelex.pipeline.execute import execute_pipeline
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventProperty
from pipelex.tools.misc.file_utils import ensure_directory_for_file_path, get_incremental_file_path, save_text_to_path
from pipelex.tools.misc.json_utils import load_json_dict_from_path, save_as_json_to_path

if TYPE_CHECKING:
    from pipelex.client.protocol import PipelineInputs

build_app = typer.Typer(help="Build working pipelines from natural language requirements", no_args_is_help=True)

"""
Today's example:
pipelex build pipe "Imagine a cute animal mascot for a startup based on its elevator pitch"
pipelex build pipe "Imagine a cute animal mascot for a startup based on its elevator pitch and some brand guidelines"
pipelex build pipe "Imagine a cute animal mascot for a startup based on its elevator pitch and some brand guidelines, \
    include 3 variants of the ideas and 2 variants of each prompt"
pipelex build pipe "Imagine a cute animal mascot for a startup based on its elevator pitch \
    and some brand guidelines, propose 2 different ideas, and for each, 3 style variants in the image generation prompt, \
        at the end we want the rendered image" --output results/mascot.plx

pipelex build pipe "Given an expense report, apply company rules"
pipelex build pipe "Take a CV in a PDF file, a Job offer text, and analyze if they match"
pipelex build pipe "Take a CV in a PDF file and a Job offer text, analyze if they match and generate 5 questions for the interview"
pipelex build pipe "Take a CV and Job offer in PDF, analyze if they match and generate 5 questions for the interview"

pipelex build pipe \
    "Take a Job offer text and a bunch of CVs (PDF), analyze how each CV matches the Job offer and generate 5 questions for each interview"

pipelex build partial "Given an expense report, apply company rules" -o results/generated.json
pipelex build flow "Given an expense report, apply company rules" -o results/flow.json

Other ideas:
pipelex build pipe "Take a photo as input, and render the opposite of the photo, don't structure anything, use only text content, be super concise"
pipelex build pipe "Take a photo as input, and render the opposite of the photo"
pipelex build pipe "Given an RDFP PDF, build a compliance matrix"
pipelex build pipe "Given a theme, write a Haiku"
"""

COMMAND = "build"

SUB_COMMAND_PIPE = "pipe"
SUB_COMMAND_RUNNER = "runner"
SUB_COMMAND_INPUTS = "inputs"
SUB_COMMAND_ONE_SHOT_PIPE = "one-shot-pipe"
SUB_COMMAND_PARTIAL_PIPE = "partial-pipe"


@build_app.command(SUB_COMMAND_PIPE, help="Build a Pipelex bundle with one validation/fix loop correcting deterministic issues")
def build_pipe_cmd(
    prompt: Annotated[
        str,
        typer.Argument(help="Prompt describing what the pipeline should do"),
    ],
    builder_pipe: Annotated[
        str,
        typer.Option("--builder-pipe", help="Builder pipe to use for generating the pipeline"),
    ] = "pipe_builder",
    output_path: Annotated[
        str,
        typer.Option("--output", "-o", help="Path to save the generated PLX file"),
    ] = "./results/generated_pipeline.plx",
    no_output: Annotated[
        bool,
        typer.Option("--no-output", help="Skip saving the pipeline to file"),
    ] = False,
) -> None:
    try:
        pipelex_instance = Pipelex.make(integration_mode=IntegrationMode.CLI)
    except LibraryLoadingError as library_loading_error:
        handle_validation_error(exc=library_loading_error, context=ErrorContext.VALIDATION_BEFORE_BUILD_PIPE)
    except ModelDeckPresetValidatonError as model_deck_error:
        handle_model_deck_preset_error(model_deck_error, context=ErrorContext.VALIDATION_BEFORE_BUILD_PIPE)

    typer.secho("🔥 Starting pipe builder... 🚀\n", fg=typer.colors.GREEN)

    async def run_pipeline():
        if no_output:
            typer.secho("\n⚠️  Pipeline will not be saved to file (--no-output specified)", fg=typer.colors.YELLOW)
        elif not output_path:
            typer.secho("\n🛑  Cannot save a pipeline to an empty file name", fg=typer.colors.RED)
            raise typer.Exit(1)
        else:
            ensure_directory_for_file_path(file_path=output_path)

        builder_loop = BuilderLoop()
        # Save to file unless explicitly disabled with --no-output
        if no_output:
            typer.secho("\n⚠️  Pipeline not saved to file (--no-output specified)", fg=typer.colors.YELLOW)
            return

        try:
            pipelex_bundle_spec = await builder_loop.build_and_fix(pipe_code=builder_pipe, inputs={"brief": prompt})
        except PipeBuilderError as exc:
            msg = f"Builder loop: Failed to execute pipeline: {exc}."
            if exc.working_memory:
                failure_memory_path = get_incremental_file_path(
                    base_path="results",
                    base_name="failure_memory",
                    extension="json",
                )
                save_as_json_to_path(object_to_save=exc.working_memory.smart_dump(), path=failure_memory_path)
                typer.secho(f"❌ {msg}", fg=typer.colors.RED)
                typer.secho(f"❌ Failure memory saved to: {failure_memory_path}", fg=typer.colors.RED)
            else:
                typer.secho(f"❌ {msg}", fg=typer.colors.RED)
                typer.secho("❌ No failure memory available", fg=typer.colors.RED)
            raise typer.Exit(1) from exc
        plx_content = PlxFactory.make_plx_content(blueprint=pipelex_bundle_spec.to_blueprint())
        save_text_to_path(text=plx_content, path=output_path)
        typer.secho(f"\n✅ Pipeline saved to: {output_path}", fg=typer.colors.GREEN)

        # Generate input JSON for the main pipe
        main_pipe_code = pipelex_bundle_spec.main_pipe
        if main_pipe_code:
            try:
                # Load the bundle from the file we just saved to register the pipe
                _ = await load_and_validate_bundle(output_path)
                pipe = get_required_pipe(pipe_code=main_pipe_code)
                inputs_json_str = generate_input_memory_json_string(pipe.inputs, indent=2)
                inputs_json_path = "results/inputs.json"
                ensure_directory_for_file_path(file_path=inputs_json_path)
                save_text_to_path(text=inputs_json_str, path=inputs_json_path)
                typer.secho(f"✅ Input example saved to: {inputs_json_path}", fg=typer.colors.GREEN)
            except Exception as exc:
                typer.secho(f"⚠️  Warning: Could not generate input JSON: {exc}", fg=typer.colors.YELLOW)

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=PACKAGE_VERSION)
            tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} {SUB_COMMAND_PIPE}")

            start_time = time.time()
            asyncio.run(run_pipeline())
            end_time = time.time()
            typer.secho(f"\n✅ Pipeline built in {end_time - start_time:.2f} seconds", fg=typer.colors.GREEN)

            get_report_delegate().generate_report()

    except PipeOperatorModelChoiceError as exc:
        handle_model_choice_error(exc, context=ErrorContext.BUILD)

    except PipeOperatorModelAvailabilityError as exc:
        handle_model_availability_error(exc, context=ErrorContext.BUILD)

    finally:
        pipelex_instance.teardown()


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
        typer.Option("--output", "-o", help="Path to save the generated Python file, defaults to 'results/run_{pipe_code}.py'"),
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
        if bundle_path:
            try:
                bundle_blueprint = await load_and_validate_bundle(bundle_path)
                if not pipe_code:
                    main_pipe_code = bundle_blueprint.main_pipe
                    if not main_pipe_code:
                        typer.secho(f"Bundle '{bundle_path}' does not declare a main_pipe", fg=typer.colors.RED, err=True)
                        raise typer.Exit(1)
                    pipe_code = main_pipe_code
                    typer.echo(f"Using main pipe '{pipe_code}' from bundle '{bundle_path}'")
                else:
                    typer.echo(f"Using pipe '{pipe_code}' from bundle '{bundle_path}'")
            except FileNotFoundError as exc:
                typer.secho(f"Failed to load bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from exc
            except PipelexBundleError as exc:
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
            pipe = get_required_pipe(pipe_code=pipe_code)
        except Exception as exc:
            typer.secho(f"❌ Error: Could not find pipe '{pipe_code}': {exc}", fg=typer.colors.RED)
            raise typer.Exit(1) from exc

        # Generate the code
        try:
            runner_code = generate_runner_code(pipe)
        except Exception as exc:
            typer.secho(f"❌ Error generating runner code: {exc}", fg=typer.colors.RED)
            raise typer.Exit(1) from exc

        # Determine output path
        final_output_path = output_path or get_incremental_file_path(
            base_path="results",
            base_name=f"run_{pipe_code}",
            extension="py",
        )

        # Save the file
        try:
            ensure_directory_for_file_path(file_path=final_output_path)
            save_text_to_path(text=runner_code, path=final_output_path)
            typer.secho(f"✅ Generated runner file: {final_output_path}", fg=typer.colors.GREEN)
        except Exception as exc:
            typer.secho(f"❌ Error saving file: {exc}", fg=typer.colors.RED)
            raise typer.Exit(1) from exc

    try:
        pipelex_instance = Pipelex.make(integration_mode=IntegrationMode.CLI)
    except LibraryLoadingError as library_loading_error:
        handle_validation_error(exc=library_loading_error, context=ErrorContext.VALIDATION_BEFORE_BUILD_RUNNER)
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
        typer.Option("--output", "-o", help="Path to save the generated JSON file, defaults to 'results/inputs.json'"),
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
                bundle_blueprint = await load_and_validate_bundle(bundle_path)
                if not pipe_code:
                    main_pipe_code = bundle_blueprint.main_pipe
                    if not main_pipe_code:
                        typer.secho(f"Bundle '{bundle_path}' does not declare a main_pipe", fg=typer.colors.RED, err=True)
                        raise typer.Exit(1)
                    pipe_code = main_pipe_code
                    typer.echo(f"Using main pipe '{pipe_code}' from bundle '{bundle_path}'")
                else:
                    typer.echo(f"Using pipe '{pipe_code}' from bundle '{bundle_path}'")
            except FileNotFoundError as exc:
                typer.secho(f"Failed to load bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from exc
            except PipelexBundleError as exc:
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
            pipe = get_required_pipe(pipe_code=pipe_code)
        except Exception as exc:
            typer.secho(f"❌ Error: Could not find pipe '{pipe_code}': {exc}", fg=typer.colors.RED)
            raise typer.Exit(1) from exc

        # Generate the input JSON
        try:
            inputs_json_str = generate_input_memory_json_string(pipe.inputs, indent=2)
        except Exception as exc:
            typer.secho(f"❌ Error generating input JSON: {exc}", fg=typer.colors.RED)
            raise typer.Exit(1) from exc

        # Determine output path
        final_output_path = output_path or "results/inputs.json"

        # Save the file
        try:
            ensure_directory_for_file_path(file_path=final_output_path)
            save_text_to_path(text=inputs_json_str, path=final_output_path)
            typer.secho(f"✅ Generated input JSON file: {final_output_path}", fg=typer.colors.GREEN)
        except Exception as exc:
            typer.secho(f"❌ Error saving file: {exc}", fg=typer.colors.RED)
            raise typer.Exit(1) from exc

    try:
        pipelex_instance = Pipelex.make(integration_mode=IntegrationMode.CLI)
    except LibraryLoadingError as library_loading_error:
        handle_validation_error(exc=library_loading_error, context=ErrorContext.VALIDATION_BEFORE_BUILD_INPUTS)
    except ModelDeckPresetValidatonError as model_deck_error:
        handle_model_deck_preset_error(model_deck_error, context=ErrorContext.VALIDATION_BEFORE_BUILD_INPUTS)

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


@build_app.command(SUB_COMMAND_ONE_SHOT_PIPE, help="Developer utility for contributors: deliver pipeline in one shot, without validation loop")
def build_one_shot_cmd(
    brief: Annotated[
        str,
        typer.Argument(help="Brief description of what the pipeline should do"),
    ],
    builder_pipe: Annotated[
        str,
        typer.Option("--builder-pipe", help="Builder pipe to use for generating the pipeline"),
    ] = "pipe_builder",
    output_path: Annotated[
        str,
        typer.Option("--output", "-o", help="Path to save the generated PLX file"),
    ] = "./results/generated_pipeline.plx",
    no_output: Annotated[
        bool,
        typer.Option("--no-output", help="Skip saving the pipeline to file"),
    ] = False,
) -> None:
    try:
        pipelex_instance = Pipelex.make(integration_mode=IntegrationMode.CLI)
    except LibraryLoadingError as library_loading_error:
        handle_validation_error(exc=library_loading_error, context=ErrorContext.VALIDATION_BEFORE_BUILD_ONE_SHOT)
    except ModelDeckPresetValidatonError as model_deck_error:
        handle_model_deck_preset_error(model_deck_error, context=ErrorContext.VALIDATION_BEFORE_BUILD_ONE_SHOT)

    typer.secho("🔥 Starting pipe builder... 🚀\n", fg=typer.colors.GREEN)

    async def run_pipeline():
        if no_output:
            typer.secho("\n⚠️  Pipeline will not be saved to file (--no-output specified)", fg=typer.colors.YELLOW)
        elif not output_path:
            typer.secho("\n🛑  Cannot save a pipeline to an empty file name", fg=typer.colors.RED)
            raise typer.Exit(1)
        else:
            ensure_directory_for_file_path(file_path=output_path)

        try:
            pipe_output = await execute_pipeline(
                pipe_code=builder_pipe,
                inputs={"brief": brief},
            )
        except PipelineExecutionError as exc:
            typer.secho(f"Failed to execute pipeline: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc
        pretty_print(pipe_output, title="Pipe Output")

        # Save to file unless explicitly disabled with --no-output
        if no_output:
            typer.secho("\n⚠️  Pipeline not saved to file (--no-output specified)", fg=typer.colors.YELLOW)
            return

        pipelex_bundle_spec = pipe_output.working_memory.get_stuff_as(name="pipelex_bundle_spec", content_type=PipelexBundleSpec)
        plx_content = PlxFactory.make_plx_content(blueprint=pipelex_bundle_spec.to_blueprint())
        save_text_to_path(text=plx_content, path=output_path)
        typer.secho(f"\n✅ Pipeline saved to: {output_path}", fg=typer.colors.GREEN)

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=PACKAGE_VERSION)
            tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} {SUB_COMMAND_ONE_SHOT_PIPE}")

            start_time = time.time()
            asyncio.run(run_pipeline())
            end_time = time.time()
            typer.secho(f"\n✅ Pipeline built in {end_time - start_time:.2f} seconds", fg=typer.colors.GREEN)

            get_report_delegate().generate_report()

    except PipeOperatorModelChoiceError as exc:
        handle_model_choice_error(exc, context=ErrorContext.BUILD)

    except PipeOperatorModelAvailabilityError as exc:
        handle_model_availability_error(exc, context=ErrorContext.BUILD)

    finally:
        pipelex_instance.teardown()


@build_app.command(
    SUB_COMMAND_PARTIAL_PIPE,
    help="Developer utility for contributors: deliver a partial pipeline specification (not an actual bundle) and save it as JSON",
)
def build_partial_cmd(
    inputs: Annotated[
        str,
        typer.Argument(help="Inline brief or path to JSON file with inputs"),
    ],
    builder_pipe: Annotated[
        str,
        typer.Option("--builder-pipe", help="Builder pipe to use for generating the pipeline"),
    ] = "pipe_builder",
    output_dir_path: Annotated[
        str,
        typer.Option("--output", "-o", help="Path to save the generated PLX file"),
    ] = "./results",
    output_base_name: Annotated[
        str,
        typer.Option("--output-file-name", "-b", help="Name of the generated JSON file"),
    ] = "partial_pipe",
    extension: Annotated[
        str,
        typer.Option("--extension", "-e", help="Extension of the generated file"),
    ] = "json",
    no_output: Annotated[
        bool,
        typer.Option("--no-output", help="Skip saving the pipeline to file"),
    ] = False,
) -> None:
    try:
        pipelex_instance = Pipelex.make(integration_mode=IntegrationMode.CLI)
    except LibraryLoadingError as library_loading_error:
        handle_validation_error(exc=library_loading_error, context=ErrorContext.VALIDATION_BEFORE_BUILD_PARTIAL)
    except ModelDeckPresetValidatonError as model_deck_error:
        handle_model_deck_preset_error(model_deck_error, context=ErrorContext.VALIDATION_BEFORE_BUILD_PARTIAL)

    typer.secho("🔥 Starting pipe builder... 🚀\n", fg=typer.colors.GREEN)

    async def run_pipeline():
        output_path: str | None = None
        if no_output:
            typer.secho("\n⚠️  Pipeline will not be saved to file (--no-output specified)", fg=typer.colors.YELLOW)
        else:
            output_path = get_incremental_file_path(
                base_path=output_dir_path,
                base_name=output_base_name,
                extension=extension,
            )
            ensure_directory_for_file_path(file_path=output_path)

        pipeline_inputs: PipelineInputs | None = None
        if inputs.endswith(".json"):
            pipeline_inputs = load_json_dict_from_path(inputs)
        else:
            pipeline_inputs = {"brief": inputs}
        try:
            pipe_output = await execute_pipeline(
                pipe_code=builder_pipe,
                inputs=pipeline_inputs,
            )
        except PipelineExecutionError as exc:
            typer.secho(f"Failed to execute pipeline: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc
        # Save to file unless explicitly disabled with --no-output
        if output_path:
            match extension:
                case "md":
                    markdown_output = pipe_output.main_stuff.content.rendered_markdown()
                    save_text_to_path(text=markdown_output, path=output_path)
                case "txt":
                    text_output = pipe_output.main_stuff.content.rendered_plain()
                    save_text_to_path(text=text_output, path=output_path)
                case "html":
                    html_output = pipe_output.main_stuff.content.rendered_html()
                    save_text_to_path(text=html_output, path=output_path)
                case "json":
                    json_output = pipe_output.main_stuff.content.smart_dump()
                    save_as_json_to_path(object_to_save=json_output, path=output_path)
                case _:
                    json_output = pipe_output.main_stuff.content.smart_dump()
                    save_as_json_to_path(object_to_save=json_output, path=output_path)
            typer.secho(f"\n✅ Pipeline saved to: {output_path}", fg=typer.colors.GREEN)
        else:
            typer.secho("\n⚠️  Pipeline not saved to file (--no-output specified)", fg=typer.colors.YELLOW)

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=PACKAGE_VERSION)
            tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} {SUB_COMMAND_PARTIAL_PIPE}")

            start_time = time.time()
            asyncio.run(run_pipeline())
            end_time = time.time()
            typer.secho(f"\n✅ Pipeline built in {end_time - start_time:.2f} seconds", fg=typer.colors.GREEN)

            get_report_delegate().generate_report()

    except PipeOperatorModelChoiceError as exc:
        handle_model_choice_error(exc, context=ErrorContext.BUILD)

    except PipeOperatorModelAvailabilityError as exc:
        handle_model_availability_error(exc, context=ErrorContext.BUILD)

    finally:
        pipelex_instance.teardown()
