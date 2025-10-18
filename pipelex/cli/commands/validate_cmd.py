from __future__ import annotations

import asyncio
from typing import Annotated

import click
import typer

from pipelex import log
from pipelex.builder.builder import load_and_validate_bundle
from pipelex.builder.builder_errors import PipelexBundleError
from pipelex.exceptions import PipeInputError
from pipelex.hub import get_pipes, get_required_pipe
from pipelex.pipe_run.dry_run import dry_run_pipe, dry_run_pipes
from pipelex.pipelex import Pipelex


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
        pipelex_instance = Pipelex.make()

        if bundle_path:
            # When validating a bundle, load_pipe_from_bundle validates ALL pipes in the bundle
            try:
                await load_and_validate_bundle(bundle_path)
                if not pipe_code:
                    typer.secho(f"✅ Successfully validated all pipes in bundle '{bundle_path}'", fg=typer.colors.GREEN)
                else:
                    typer.secho(f"✅ Successfully validated all pipes in bundle '{bundle_path}' (including '{pipe_code}')", fg=typer.colors.GREEN)
            except FileNotFoundError as exc:
                typer.secho(f"Failed to load bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from exc
            except PipelexBundleError as exc:
                typer.secho(f"Failed to validate bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from exc
            except PipeInputError as exc:
                typer.secho(f"Failed to validate bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
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
