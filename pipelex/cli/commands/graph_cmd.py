"""CLI command to dry run a pipe and output the execution graph as JSON."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import click
import typer
from posthog import tag

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
from pipelex.observability.graphspec import GraphSpec, graphspec_to_json, save_graphspec
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipe_run.dry_run_with_graph import dry_run_pipe_with_graph
from pipelex.pipelex import Pipelex
from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventProperty
from pipelex.tools.misc.package_utils import get_package_version

COMMAND = "graph"


def graph_cmd(
    target: Annotated[
        str | None,
        typer.Argument(help="Pipe code or bundle file path (auto-detected based on .plx extension)"),
    ] = None,
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to trace (optional when using --bundle)"),
    ] = None,
    bundle: Annotated[
        str | None,
        typer.Option("--bundle", help="Bundle file path (.plx) - traces its main_pipe unless you specify a pipe code"),
    ] = None,
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Path to save output JSON, defaults to stdout if not specified"),
    ] = None,
) -> None:
    """Dry run a pipe and output its execution graph as JSON.

    This command validates and dry runs a pipe, capturing the execution graph
    structure as a GraphSpec JSON. Useful for visualizing pipe structure
    and debugging execution flow.

    Examples:
        pipelex graph my_pipe
        pipelex graph my_bundle.plx
        pipelex graph --bundle my_bundle.plx
        pipelex graph --bundle my_bundle.plx --pipe my_pipe
        pipelex graph my_pipe --output graph.json
    """
    # Validate mutual exclusivity
    provided_options = sum([target is not None, pipe is not None, bundle is not None])
    if provided_options == 0:
        ctx: click.Context = click.get_current_context()
        typer.echo(ctx.get_help())
        raise typer.Exit(0)

    # Analyze options and determine pipe code and bundle path
    pipe_code: str | None = None
    bundle_path: str | None = None

    if target:
        if target.endswith(".plx"):
            bundle_path = target
            if bundle:
                typer.secho(
                    "Failed to graph: cannot use option --bundle if you're already passing a bundle file (.plx) as positional argument",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(1)
        else:
            pipe_code = target
            if pipe:
                typer.secho(
                    "Failed to graph: cannot use option --pipe if you're already passing a pipe code as positional argument",
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
        typer.secho("Failed to graph: no pipe code or bundle file specified", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    async def generate_graph(pipe_code: str | None = None, bundle_path: str | None = None) -> GraphSpec:
        resolved_pipe_code: str

        if bundle_path:
            try:
                validate_bundle_result = await validate_bundle(plx_file_path=bundle_path)
                if not pipe_code:
                    main_pipe_code = validate_bundle_result.blueprints[0].main_pipe
                    if not main_pipe_code:
                        typer.secho(f"Bundle '{bundle_path}' does not declare a main_pipe", fg=typer.colors.RED, err=True)
                        raise typer.Exit(1)
                    resolved_pipe_code = main_pipe_code
                    typer.echo(f"Graphing bundle '{bundle_path}' • main pipe: '{resolved_pipe_code}'", err=True)
                else:
                    resolved_pipe_code = pipe_code
                    typer.echo(f"Graphing bundle '{bundle_path}' • pipe: '{resolved_pipe_code}'", err=True)
            except FileNotFoundError as exc:
                typer.secho(f"Failed to load bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from exc
            except ValidateBundleError as bundle_error:
                handle_validate_bundle_error(bundle_error, bundle_path=bundle_path)
        elif pipe_code:
            resolved_pipe_code = pipe_code
            typer.echo(f"Graphing pipe '{resolved_pipe_code}'", err=True)
            library_manager = get_library_manager()
            library_id, _ = library_manager.open_library()
            set_current_library(library_id=library_id)
            library_manager.load_libraries(library_id=library_id, library_dirs=[Path.cwd()])
        else:
            typer.secho("Failed to graph: no pipe code or bundle specified", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)

        # Get the pipe and run with graph tracing
        pipe_obj = get_required_pipe(pipe_code=resolved_pipe_code)
        return await dry_run_pipe_with_graph(pipe=pipe_obj)

    # Initialize Pipelex
    make_pipelex_for_cli(context=ErrorContext.VALIDATION)

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
            tag(name=EventProperty.CLI_COMMAND, value=COMMAND)

            graph_spec = asyncio.run(generate_graph(pipe_code=pipe_code, bundle_path=bundle_path))

            # Output the graph
            if output:
                save_graphspec(graph_spec, Path(output))
                typer.secho(f"✅ Graph saved to: {output}", fg=typer.colors.GREEN, err=True)
            else:
                # Output to stdout
                json_str = graphspec_to_json(graph_spec)
                typer.echo(json_str)

    except PipeOperatorModelChoiceError as exc:
        handle_model_choice_error(exc, context=ErrorContext.VALIDATION)

    except PipeOperatorModelAvailabilityError as exc:
        handle_model_availability_error(exc, context=ErrorContext.VALIDATION)

    except typer.Exit:
        raise

    except Exception as exc:
        log.error(f"Error generating graph: {exc}")
        console = get_console()
        console.print("\n[bold red]Failed to generate graph[/bold red]\n")
        console.print_exception(show_locals=True)
        raise typer.Exit(1) from exc

    finally:
        Pipelex.teardown_if_needed()
