from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Annotated

import click
import typer
from rich.console import Console
from rich.syntax import Syntax

from pipelex import log, pretty_print
from pipelex.builder.builder_errors import PipelexBundleError
from pipelex.builder.builder_validation import validate_dry_run_bundle_blueprint
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.exceptions import LibraryLoadingError, PipeInputError
from pipelex.hub import get_pipes, get_required_pipe
from pipelex.pipe_run.dry_run import dry_run_pipe, dry_run_pipes
from pipelex.pipelex import Pipelex

if TYPE_CHECKING:
    from pipelex.core.validation_errors import ValidationErrorDetailsProtocol
console = Console()


def do_validate_all_libraries_and_dry_run() -> None:
    """Validate libraries and dry-run all pipes."""
    pipelex_instance = Pipelex.make()
    pipelex_instance.validate_libraries()
    asyncio.run(dry_run_pipes(pipes=get_pipes(), raise_on_failure=True))
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
        # Initialize Pipelex
        try:
            pipelex_instance = Pipelex.make()
        except LibraryLoadingError as library_loading_error:
            typer.secho(f"Failed to validate: {library_loading_error}", fg=typer.colors.RED, err=True)
            present_validation_error(details_provider=library_loading_error)
            raise typer.Exit(1) from library_loading_error

        if bundle_path:
            # When validating a bundle, load_pipe_from_bundle validates ALL pipes in the bundle
            try:
                bundle_blueprint = PipelexInterpreter.load_bundle_blueprint(bundle_path=bundle_path)
                await validate_dry_run_bundle_blueprint(bundle_blueprint=bundle_blueprint)
                if not pipe_code:
                    typer.secho(f"✅ Successfully validated all pipes in bundle '{bundle_path}'", fg=typer.colors.GREEN)
                else:
                    typer.secho(f"✅ Successfully validated all pipes in bundle '{bundle_path}' (including '{pipe_code}')", fg=typer.colors.GREEN)
            except FileNotFoundError as exc:
                typer.secho(f"Failed to load bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
                console.print(exc)
                raise typer.Exit(1) from exc
            except PipelexBundleError as bundle_error:
                typer.secho(f"\n❌ Failed to validate bundle '{bundle_path}':", fg=typer.colors.RED, err=True)
                present_validation_error(details_provider=bundle_error)
                raise typer.Exit(1) from bundle_error
            except PipeInputError as exc:
                typer.secho(f"\n❌ Failed to validate bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
                console.print(exc)
                raise typer.Exit(1) from exc
        elif pipe_code:
            # Validate a single pipe by code
            typer.echo(f"Validating pipe '{pipe_code}'...")
            pipelex_instance.validate_libraries()
            await dry_run_pipe(
                get_required_pipe(pipe_code=pipe_code),
                raise_on_failure=True,
            )
            typer.secho(f"✅ Successfully validated pipe '{pipe_code}'", fg=typer.colors.GREEN)
        else:
            typer.secho("Failed to validate: no pipe code or bundle specified", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)

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
