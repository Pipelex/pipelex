from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import click
import typer
from posthog import tag
from rich.traceback import Traceback

from pipelex import log
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import (
    ErrorContext,
    handle_model_availability_error,
    handle_model_choice_error,
    handle_validate_bundle_error,
)
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.hub import get_console, get_library_manager, get_required_pipe, get_telemetry_manager, set_current_library
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipe_run.dry_run import dry_run_pipe, dry_run_pipes
from pipelex.pipelex import Pipelex
from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventName, EventProperty
from pipelex.tools.misc.package_utils import get_package_version

COMMAND = "validate"


def do_validate_all_libraries_and_dry_run(library_dirs: list[Path] | None = None) -> None:
    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
            tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} all")

            library_manager = get_library_manager()
            library_id, library = library_manager.open_library()
            set_current_library(library_id=library_id)
            library_manager.load_libraries(library_id=library_id, library_dirs=library_dirs or [Path.cwd()])

            pipes = library.get_pipe_library().get_pipes()
            for pipe in pipes:
                pipe.validate_with_libraries()

            get_telemetry_manager().track_event(EventName.PIPE_DRY_RUN, properties={EventProperty.NB_PIPES: len(pipes)})

            asyncio.run(dry_run_pipes(pipes=pipes, raise_on_failure=True))
            log.info("Setup sequence passed OK, config and pipelines are validated.")
    except PipeOperatorModelAvailabilityError as exc:
        handle_model_availability_error(exc, context=ErrorContext.VALIDATION)
    except PipeOperatorModelChoiceError as exc:
        handle_model_choice_error(exc, context=ErrorContext.VALIDATION)


def validate_cmd(
    target: Annotated[
        str | None,
        typer.Argument(help="Pipe code, bundle file path (auto-detected based on .plx extension), or 'all' to validate all pipes"),
    ] = None,
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to validate (optional when using --bundle)"),
    ] = None,
    bundle: Annotated[
        str | None,
        typer.Option("--bundle", help="Bundle file path (.plx) - validates all pipes in the bundle"),
    ] = None,
    library_dir: Annotated[
        list[str] | None,
        typer.Option(
            "--library-dir",
            "-L",
            help="Directory to search for pipe definitions (.plx files). Can be specified multiple times.",
        ),
    ] = None,
) -> None:
    """Validate and dry run a pipe or a bundle or all pipes.

    Examples:
        pipelex validate my_pipe
        pipelex validate my_bundle.plx
        pipelex validate --bundle my_bundle.plx
        pipelex validate --bundle my_bundle.plx --pipe my_pipe
        pipelex validate all
    """
    # Check for "all" keyword
    if target == "all" and not pipe and not bundle:
        try:
            make_pipelex_for_cli(context=ErrorContext.VALIDATION)
            library_dirs_paths = [Path(lib_dir) for lib_dir in library_dir] if library_dir else None
            do_validate_all_libraries_and_dry_run(library_dirs=library_dirs_paths)
        finally:
            Pipelex.teardown_if_needed()
        return

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
                    "Failed to validate: cannot use option --bundle if you're already passing a bundle file (.plx) as positional argument",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(1)
        else:
            pipe_code = target
            if pipe:
                typer.secho(
                    "Failed to validate: cannot use option --pipe if you're already passing a pipe code as positional argument",
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
        typer.secho("Failed to validate: no pipe code or bundle file specified", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    async def validate_pipe(pipe_code: str | None = None, bundle_path: str | None = None):
        if bundle_path:
            try:
                await validate_bundle(plx_file_path=bundle_path)
                typer.secho(f"✅ Successfully validated bundle '{bundle_path}'", fg=typer.colors.GREEN)
            except FileNotFoundError as exc:
                get_console().print(Traceback())
                typer.secho(f"Failed to load bundle '{bundle_path}':", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from exc
            except ValidateBundleError as bundle_error:
                handle_validate_bundle_error(bundle_error, bundle_path=bundle_path)
        elif pipe_code:
            typer.echo(f"Validating pipe '{pipe_code}'...")
            library_manager = get_library_manager()
            library_id, _ = library_manager.open_library()
            set_current_library(library_id=library_id)
            library_dirs_paths = [Path(lib_dir) for lib_dir in library_dir] if library_dir else [Path.cwd()]
            library_manager.load_libraries(library_id=library_id, library_dirs=library_dirs_paths)

            pipe = get_required_pipe(pipe_code=pipe_code)
            get_telemetry_manager().track_event(EventName.PIPE_DRY_RUN, properties={EventProperty.PIPE_TYPE: pipe.type})
            await dry_run_pipe(
                pipe,
                raise_on_failure=True,
            )
            typer.secho(f"✅ Successfully validated pipe '{pipe_code}'", fg=typer.colors.GREEN)
        else:
            typer.secho("Failed to validate: no pipe code or bundle specified", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)

    make_pipelex_for_cli(context=ErrorContext.VALIDATION)

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
            if bundle_path:
                tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} bundle")
            else:
                tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} pipe")

            asyncio.run(validate_pipe(pipe_code=pipe_code, bundle_path=bundle_path))
    except PipeOperatorModelChoiceError as exc:
        handle_model_choice_error(exc, context=ErrorContext.VALIDATION)
    except PipeOperatorModelAvailabilityError as exc:
        handle_model_availability_error(exc, context=ErrorContext.VALIDATION)
    finally:
        Pipelex.teardown_if_needed()
