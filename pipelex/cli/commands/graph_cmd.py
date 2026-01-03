"""CLI command to dry run a pipe and output the execution graph."""

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
from pipelex.observability.graphspec.html_renderer import render_mermaid_html
from pipelex.observability.graphspec.mermaid import VALID_DIRECTIONS, graphspec_to_mermaid
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipe_run.dry_run_with_graph import dry_run_pipe_with_graph
from pipelex.pipelex import Pipelex
from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventProperty
from pipelex.tools.misc.package_utils import get_package_version

COMMAND = "graph"


def _resolve_output_paths(
    out: str | None,
    generate_json: bool,
    generate_mermaid: bool,
    generate_html: bool,
) -> tuple[Path | None, Path | None, Path | None]:
    """Resolve output paths based on the --out option.

    Args:
        out: The --out option value (path, directory, or stem).
        generate_json: Whether JSON output is requested.
        generate_mermaid: Whether Mermaid output is requested.
        generate_html: Whether HTML output is requested.

    Returns:
        Tuple of (json_path, mermaid_path, html_path). None means stdout/skip.
    """
    if out is None:
        # Default behavior: JSON to stdout, others to CWD if requested
        json_path: Path | None = None  # stdout
        mermaid_path = Path("graph.mmd") if generate_mermaid else None
        html_path = Path("graph.html") if generate_html else None
        return json_path, mermaid_path, html_path

    out_path = Path(out)

    # Case 1: --out is an existing directory
    if out_path.is_dir():
        json_path = out_path / "graph.json" if generate_json else None
        mermaid_path = out_path / "graph.mmd" if generate_mermaid else None
        html_path = out_path / "graph.html" if generate_html else None
        return json_path, mermaid_path, html_path

    # Case 2: --out ends with .json - use as JSON path, derive siblings
    if out.endswith(".json"):
        stem = out_path.stem
        parent = out_path.parent
        json_path = out_path if generate_json else None
        mermaid_path = parent / f"{stem}.mmd" if generate_mermaid else None
        html_path = parent / f"{stem}.html" if generate_html else None
        return json_path, mermaid_path, html_path

    # Case 3: --out is a stem base
    stem = out_path.name
    parent = out_path.parent if out_path.parent != out_path else Path.cwd()
    json_path = parent / f"{stem}.json" if generate_json else None
    mermaid_path = parent / f"{stem}.mmd" if generate_mermaid else None
    html_path = parent / f"{stem}.html" if generate_html else None
    return json_path, mermaid_path, html_path


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
        typer.Option("--output", "-o", help="[Deprecated: use --out] Path to save output JSON"),
    ] = None,
    out: Annotated[
        str | None,
        typer.Option("--out", help="Output path, directory, or stem (e.g., 'graph', './out/', 'result.json')"),
    ] = None,
    mermaid: Annotated[
        bool,
        typer.Option("--mermaid", help="Also generate Mermaid flowchart (.mmd file)"),
    ] = False,
    html: Annotated[
        bool,
        typer.Option("--html", help="Also generate HTML with embedded Mermaid (.html file)"),
    ] = False,
    direction: Annotated[
        str,
        typer.Option("--direction", help=f"Mermaid flowchart direction ({', '.join(sorted(VALID_DIRECTIONS))})"),
    ] = "TD",
    no_data_edges: Annotated[
        bool,
        typer.Option("--no-data-edges", help="Exclude data flow edges from Mermaid output"),
    ] = False,
    no_contains_edges: Annotated[
        bool,
        typer.Option("--no-contains-edges", help="Exclude parent-child (contains) edges from Mermaid output"),
    ] = False,
) -> None:
    """Dry run a pipe and output its execution graph.

    By default, outputs JSON to stdout. Use --out to save to file(s).

    Examples:
        pipelex graph my_pipe
        pipelex graph my_pipe --out graph.json
        pipelex graph my_pipe --mermaid --html --out ./output/
        pipelex graph my_bundle.plx --mermaid --direction LR
    """
    # Handle deprecated --output flag
    if output and not out:
        out = output

    # Validate direction
    if direction not in VALID_DIRECTIONS:
        typer.secho(
            f"Invalid direction '{direction}'. Must be one of: {', '.join(sorted(VALID_DIRECTIONS))}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

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

            # Determine what outputs to generate
            generate_json = True  # Always generate JSON (either to stdout or file)
            generate_mermaid = mermaid or html  # Mermaid needed for HTML too
            generate_html = html

            # Resolve output paths
            json_path, mermaid_path, html_path = _resolve_output_paths(
                out=out,
                generate_json=generate_json,
                generate_mermaid=generate_mermaid,
                generate_html=generate_html,
            )

            # Generate and save JSON
            if json_path:
                save_graphspec(graph_spec, json_path)
                typer.secho(f"✅ JSON saved to: {json_path}", fg=typer.colors.GREEN, err=True)
            else:
                # Output JSON to stdout
                json_str = graphspec_to_json(graph_spec)
                typer.echo(json_str)

            # Generate and save Mermaid
            if generate_mermaid:
                mermaid_code = graphspec_to_mermaid(
                    graph_spec,
                    direction=direction,
                    include_data_edges=not no_data_edges,
                    include_contains_edges=not no_contains_edges,
                )
                if mermaid_path:
                    mermaid_path.write_text(mermaid_code, encoding="utf-8")
                    typer.secho(f"✅ Mermaid saved to: {mermaid_path}", fg=typer.colors.GREEN, err=True)

                # Generate and save HTML (uses mermaid_code)
                if generate_html and html_path:
                    # Determine title from pipe name
                    title = pipe_code or bundle_path or "Pipelex Graph"
                    if bundle_path:
                        title = Path(bundle_path).stem
                    html_content = render_mermaid_html(mermaid_code, title=f"Graph: {title}")
                    html_path.write_text(html_content, encoding="utf-8")
                    typer.secho(f"✅ HTML saved to: {html_path}", fg=typer.colors.GREEN, err=True)

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
