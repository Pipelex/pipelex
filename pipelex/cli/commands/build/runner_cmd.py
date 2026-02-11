import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

if TYPE_CHECKING:
    from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint

import click
import typer
from posthog import tag

from pipelex.builder.runner_code import generate_runner_code
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.commands.build.structures_cmd import generate_structures_from_blueprints
from pipelex.cli.error_handlers import (
    ErrorContext,
    handle_model_availability_error,
    handle_model_choice_error,
)
from pipelex.core.interpreter.helpers import is_pipelex_file
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.core.pipes.inputs.exceptions import PipeInputError
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.core.registry_models import CoreRegistryModels
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.hub import get_class_registry, get_func_registry, get_required_pipe, get_telemetry_manager
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import PACKAGE_VERSION
from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle
from pipelex.system.registries.class_registry_utils import ClassRegistryUtils
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventProperty
from pipelex.tools.misc.file_utils import (
    ensure_directory_for_file_path,
    save_text_to_path,
)

COMMAND = "build"
SUB_COMMAND_RUNNER = "runner"


async def prepare_runner(
    pipe_code: str | None = None,
    bundle_path: Path | None = None,
    output_path: Path | None = None,
    library_dirs: list[Path] | None = None,
):
    all_blueprints: list[PipelexBundleBlueprint] = []

    if bundle_path:
        try:
            validate_bundle_result = await validate_bundle(plx_file_path=bundle_path, library_dirs=library_dirs)
            all_blueprints.extend(validate_bundle_result.blueprints)
            first_blueprint = validate_bundle_result.blueprints[0]
            if not pipe_code:
                main_pipe_code = first_blueprint.main_pipe
                if not main_pipe_code:
                    typer.secho(
                        f"Bundle '{bundle_path}' has no main_pipe declared. Use --pipe to specify which pipe to use.",
                        fg=typer.colors.RED,
                        err=True,
                    )
                    raise typer.Exit(1)
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
    else:
        typer.secho("Failed to run: no bundle file specified", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    try:
        the_pipe = get_required_pipe(pipe_code=pipe_code)
    except Exception as exc:
        typer.secho(f"❌ Error: Could not find pipe '{pipe_code}': {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc

    # Determine output path - use target's directory
    if output_path:
        final_output_path = output_path
    else:
        # Place runner in the same directory as the MTHDS file
        bundle_dir = Path(bundle_path).parent
        final_output_path = bundle_dir / f"run_{pipe_code}.py"
    output_dir = Path(final_output_path).parent

    # Generate structures folder FIRST (before runner, since runner imports from structures)
    structures_output_dir = output_dir / "structures"
    if all_blueprints:
        get_class_registry().teardown()
        get_func_registry().teardown()
        get_class_registry().register_classes(CoreRegistryModels.get_all_models())
        generated_structures = generate_structures_from_blueprints(
            blueprints=all_blueprints,
            output_directory=structures_output_dir,
            target_path=output_dir,  # Check for existing structures in the target directory
        )
        if generated_structures:
            typer.secho(f"✅ Generated {len(generated_structures)} structure(s) in: {structures_output_dir}", fg=typer.colors.GREEN)

    # Register all structure classes from the output directory so generate_runner_code can find them
    # This includes both newly generated structures and any manually-created ones
    if structures_output_dir.exists():
        ClassRegistryUtils.register_classes_in_folder(
            folder_path=str(structures_output_dir),
            base_class=StuffContent,
            is_recursive=True,
        )
    # Also register any manually-created classes in the target directory (outside structures/)
    ClassRegistryUtils.register_classes_in_folder(
        folder_path=str(output_dir),
        base_class=StuffContent,
        is_recursive=True,
        force_exclude_dirs=[str(structures_output_dir.resolve())] if structures_output_dir.exists() else None,
    )
    get_class_registry().register_classes(CoreRegistryModels.get_all_models())

    # Determine if output is a list from any of the blueprints
    output_is_list = False
    for blueprint in all_blueprints:
        if blueprint.pipe and pipe_code in blueprint.pipe:
            pipe_blueprint = blueprint.pipe[pipe_code]
            output_parse = parse_concept_with_multiplicity(pipe_blueprint.output)
            output_is_list = output_parse.multiplicity is not None
            break

    # Determine the library directory for Pipelex.make()
    if library_dirs:
        pipelex_library_dir = str(library_dirs[0].resolve())
    elif bundle_path:
        pipelex_library_dir = str(Path(bundle_path).parent.resolve())
    else:
        pipelex_library_dir = None

    # Generate the runner code
    try:
        runner_code = generate_runner_code(pipe=the_pipe, output_multiplicity=output_is_list, library_dir=pipelex_library_dir)
    except Exception as exc:
        typer.secho(f"❌ Error generating runner code: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc

    # Save the runner file
    try:
        ensure_directory_for_file_path(file_path=str(final_output_path))
        save_text_to_path(text=runner_code, path=str(final_output_path))
        typer.secho(f"✅ Generated runner file: {final_output_path}", fg=typer.colors.GREEN)
    except Exception as exc:
        typer.secho(f"❌ Error saving file: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc


def prepare_runner_cmd(
    target: Annotated[
        str | None,
        typer.Argument(help="Bundle file path (.mthds)"),
    ] = None,
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to use (optional if the .mthds declares a main_pipe)"),
    ] = None,
    output_path: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Path to save the generated Python file (defaults to target's directory)"),
    ] = None,
    library_dirs: Annotated[
        list[str] | None,
        typer.Option("--library-dirs", "-L", help="Directories to search for pipe definitions (.mthds files). Can be specified multiple times."),
    ] = None,
) -> None:
    """Prepare a Python runner file for a pipe.

    The generated file will include:
    - All necessary imports
    - Example input values based on the pipe's input types

    Native concept types (Text, Image, Document, etc.) will be automatically handled.
    Custom concept types will have their structure recursively generated.

    Examples:
        pipelex build runner my_bundle.mthds
        pipelex build runner my_bundle.mthds --pipe my_pipe
        pipelex build runner my_bundle.mthds --output runner.py
    """
    # Show help if no target provided
    if target is None:
        ctx: click.Context = click.get_current_context()
        typer.echo(ctx.get_help())
        raise typer.Exit(0)

    # Analyze target type
    target_path = Path(target)
    output_path_path = Path(output_path) if output_path else None
    library_dirs_paths = [Path(lib_dir) for lib_dir in library_dirs] if library_dirs else None

    # Validate: target must be a .mthds file
    if not is_pipelex_file(target_path):
        typer.secho(
            f"Failed to run: '{target}' is not a .mthds file.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    pipelex_instance = make_pipelex_for_cli(context=ErrorContext.VALIDATION_BEFORE_BUILD_RUNNER)

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=PACKAGE_VERSION)
            tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} {SUB_COMMAND_RUNNER}")

            asyncio.run(prepare_runner(pipe_code=pipe, bundle_path=target_path, library_dirs=library_dirs_paths, output_path=output_path_path))

    except PipeOperatorModelChoiceError as exc:
        handle_model_choice_error(exc, context=ErrorContext.BUILD)

    except PipeOperatorModelAvailabilityError as exc:
        handle_model_availability_error(exc, context=ErrorContext.BUILD)

    finally:
        pipelex_instance.teardown()
