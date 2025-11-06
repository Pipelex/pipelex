from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import click
import typer
from posthog import new_context, tag
from rich.console import Console
from rich.syntax import Syntax
from rich.traceback import Traceback

from pipelex import log, pretty_print
from pipelex.builder.builder_errors import PipelexBundleError
from pipelex.builder.builder_validation import validate_dry_run_bundle_blueprint
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.exceptions import LibraryLoadingError, PipeInputError
from pipelex.hub import get_library_manager, get_pipes, get_required_pipe, get_telemetry_manager
from pipelex.pipe_run.dry_run import dry_run_pipe, dry_run_pipes
from pipelex.pipelex import Pipelex
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventName, EventProperty
from pipelex.tools.misc.package_utils import get_package_version

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_abstract import PipeAbstract
    from pipelex.core.validation_errors import ValidationErrorDetailsProtocol

console = Console()

COMMAND = "validate"


def do_validate_all_libraries_and_dry_run() -> None:
    """Validate libraries and dry-run all pipes."""
    pipelex_instance = Pipelex.make(integration_mode=IntegrationMode.CLI)
    with new_context():
        tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
        tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
        tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} all")

        pipelex_instance.validate_libraries()
        pipes = get_pipes()
        get_telemetry_manager().track_event(EventName.PIPE_DRY_RUN, properties={EventProperty.NB_PIPES: len(pipes)})
        asyncio.run(dry_run_pipes(pipes=pipes, raise_on_failure=True))
        log.info("Setup sequence passed OK, config and pipelines are validated.")


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
        do_validate_all_libraries_and_dry_run()
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
            absolute_bundle_path = str(Path(bundle_path).resolve())
            if absolute_bundle_path in get_library_manager().get_loaded_plx_paths():
                bundle_blueprint = PipelexInterpreter.load_bundle_blueprint(bundle_path=bundle_path)
                if not bundle_blueprint.pipe:
                    typer.secho(f"Failed to validate bundle '{bundle_path}': no pipes found in bundle", fg=typer.colors.RED, err=True)
                    raise typer.Exit(1)
                pipe_codes = list(bundle_blueprint.pipe.keys())
                pipes: list[PipeAbstract] = []
                for the_pipe_code in pipe_codes:
                    pipes.append(get_required_pipe(pipe_code=the_pipe_code))
                await dry_run_pipes(pipes=pipes, raise_on_failure=True)
                typer.secho(f"✅ Successfully validated all pipes in bundle '{bundle_path}'", fg=typer.colors.GREEN)
                return
            # When validating a bundle, load_pipe_from_bundle validates ALL pipes in the bundle
            try:
                bundle_blueprint = PipelexInterpreter.load_bundle_blueprint(bundle_path=bundle_path)
                get_telemetry_manager().track_event(
                    EventName.BUNDLE_DRY_RUN,
                    properties={EventProperty.NB_PIPES: bundle_blueprint.nb_pipes, EventProperty.NB_CONCEPTS: bundle_blueprint.nb_concepts},
                )
                await validate_dry_run_bundle_blueprint(bundle_blueprint=bundle_blueprint)
                if not pipe_code:
                    typer.secho(f"✅ Successfully validated all pipes in bundle '{bundle_path}'", fg=typer.colors.GREEN)
                else:
                    typer.secho(f"✅ Successfully validated all pipes in bundle '{bundle_path}' (including '{pipe_code}')", fg=typer.colors.GREEN)
            except FileNotFoundError as exc:
                console.print(Traceback())
                typer.secho(f"Failed to load bundle '{bundle_path}':", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from exc
            except PipelexBundleError as bundle_error:
                console.print(Traceback())
                typer.secho(f"\n❌ Failed to validate bundle '{bundle_path}':", fg=typer.colors.RED, err=True)
                present_validation_error(details_provider=bundle_error)
                raise typer.Exit(1) from bundle_error
            except PipeInputError as exc:
                console.print(Traceback())
                typer.secho(f"\n❌ Failed to validate bundle '{bundle_path}':", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from exc
        elif pipe_code:
            # Validate a single pipe by code
            typer.echo(f"Validating pipe '{pipe_code}'...")
            get_telemetry_manager().track_event(
                EventName.PIPE_DRY_RUN, properties={EventProperty.PIPE_TYPE: get_required_pipe(pipe_code=pipe_code).type}
            )
            pipelex_instance.validate_libraries()
            await dry_run_pipe(
                get_required_pipe(pipe_code=pipe_code),
                raise_on_failure=True,
            )
            typer.secho(f"✅ Successfully validated pipe '{pipe_code}'", fg=typer.colors.GREEN)
        else:
            typer.secho("Failed to validate: no pipe code or bundle specified", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)

    # Initialize Pipelex
    try:
        pipelex_instance = Pipelex.make(integration_mode=IntegrationMode.CLI)
    except LibraryLoadingError as library_loading_error:
        typer.secho(f"Failed to validate: {library_loading_error}", fg=typer.colors.RED, err=True)
        present_validation_error(details_provider=library_loading_error)
        raise typer.Exit(1) from library_loading_error

    with new_context():
        tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
        tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
        if bundle_path:
            tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} bundle")
        else:
            tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} pipe")

        asyncio.run(validate_pipe(pipe_code=pipe_code, bundle_path=bundle_path))


def present_validation_error(details_provider: ValidationErrorDetailsProtocol):
    console.print(details_provider)
    concept_definition_errors = details_provider.get_concept_definition_errors()
    if not concept_definition_errors:
        return
    for concept_definition_error in concept_definition_errors:
        syntax_error_data = concept_definition_error.structure_class_syntax_error_data
        if not syntax_error_data:
            continue
        message = concept_definition_error.message
        code = concept_definition_error.structure_class_python_code or ""
        highlight_lines: set[int] | None = None
        if syntax_error_data.lineno:
            highlight_lines = {syntax_error_data.lineno}
        syntax = Syntax(
            code=code,
            lexer="python",
            line_numbers=True,
            word_wrap=False,
            # theme="monokai",  # pick any theme rich knows; omit to use default
            theme="ansi_dark",  # pick any theme rich knows; omit to use default
            line_range=None,
            highlight_lines=highlight_lines,
        )
        pretty_range = ""
        if syntax_error_data.lineno and syntax_error_data.end_lineno:
            pretty_range = f"lines {syntax_error_data.lineno} to {syntax_error_data.end_lineno}"
        elif syntax_error_data.lineno:
            pretty_range = f"line {syntax_error_data.lineno}"
        if syntax_error_data.offset and syntax_error_data.end_offset:
            pretty_range += f", column {syntax_error_data.offset} to {syntax_error_data.end_offset}"
        elif syntax_error_data.offset:
            pretty_range += f", column {syntax_error_data.offset}"
        console.print(message)
        if pretty_range:
            pretty_print(f"Generated code error at {pretty_range}")
        console.print(syntax)
