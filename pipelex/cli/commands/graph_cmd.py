"""CLI commands to generate and render execution graphs."""

from __future__ import annotations

import asyncio
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

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
from pipelex.config import get_config
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.graph.graph_analysis import GraphAnalysis
from pipelex.graph.graphspec_io import graphspec_to_json, load_graphspec, save_graphspec
from pipelex.graph.mermaid import (
    collect_stuff_data_html,
    collect_stuff_data_text,
    graphspec_to_combo_mermaid,
    graphspec_to_dataflow_mermaid,
    graphspec_to_orchestration_mermaid,
)
from pipelex.graph.reactflow_html import generate_reactflow_html, generate_reactflow_html_async
from pipelex.graph.viewspec_transformer import graphspec_to_viewspec
from pipelex.hub import get_console, get_library_manager, get_required_pipe, get_telemetry_manager, set_current_library
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipe_run.dry_run_with_graph import dry_run_pipe_with_graph
from pipelex.pipelex import Pipelex
from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventProperty
from pipelex.tools.misc.chart_utils import FlowchartDirection
from pipelex.tools.misc.mermaid_utils import (
    render_mermaid_html,
    render_mermaid_html_async,
    render_mermaid_html_with_data_async,
)
from pipelex.tools.misc.package_utils import get_package_version

if TYPE_CHECKING:
    from pipelex.graph.graphspec import GraphSpec

COMMAND = "graph"

graph_app = typer.Typer(no_args_is_help=True)


def _resolve_output_paths(
    out: str | None,
    generate_json: bool,
    generate_mermaid: bool,
    generate_html: bool,
    generate_reactflow: bool = False,
) -> tuple[Path | None, Path | None, Path | None, Path | None]:
    """Resolve output paths based on the --out option.

    Args:
        out: The --out option value (path, directory, or stem).
        generate_json: Whether JSON output is requested.
        generate_mermaid: Whether Mermaid output is requested.
        generate_html: Whether HTML output is requested.
        generate_reactflow: Whether ReactFlow output is requested.

    Returns:
        Tuple of (json_path, mermaid_path, html_path, reactflow_path). None means stdout/skip.
    """
    if out is None:
        # Default behavior: JSON to stdout, others to CWD if requested
        json_path: Path | None = None  # stdout
        mermaid_path = Path("graph.mmd") if generate_mermaid else None
        html_path = Path("graph.html") if generate_html else None
        reactflow_path = Path("graph.reactflow.html") if generate_reactflow else None
        return json_path, mermaid_path, html_path, reactflow_path

    out_path = Path(out)

    # Case 1: --out is an existing directory
    if out_path.is_dir():
        json_path = out_path / "graph.json" if generate_json else None
        mermaid_path = out_path / "graph.mmd" if generate_mermaid else None
        html_path = out_path / "graph.html" if generate_html else None
        reactflow_path = out_path / "graph.reactflow.html" if generate_reactflow else None
        return json_path, mermaid_path, html_path, reactflow_path

    # Case 2: --out ends with .json - use as JSON path, derive siblings
    if out.endswith(".json"):
        stem = out_path.stem
        parent = out_path.parent
        json_path = out_path if generate_json else None
        mermaid_path = parent / f"{stem}.mmd" if generate_mermaid else None
        html_path = parent / f"{stem}.html" if generate_html else None
        reactflow_path = parent / f"{stem}.reactflow.html" if generate_reactflow else None
        return json_path, mermaid_path, html_path, reactflow_path

    # Case 3: --out is a stem base
    stem = out_path.name
    parent = out_path.parent if out_path.parent != out_path else Path.cwd()
    json_path = parent / f"{stem}.json" if generate_json else None
    mermaid_path = parent / f"{stem}.mmd" if generate_mermaid else None
    html_path = parent / f"{stem}.html" if generate_html else None
    reactflow_path = parent / f"{stem}.reactflow.html" if generate_reactflow else None
    return json_path, mermaid_path, html_path, reactflow_path


@graph_app.command("trace", help="Dry run a pipe and output its execution graph")
def graph_trace_cmd(
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
        FlowchartDirection | None,
        typer.Option("--direction", help="Flowchart direction"),
    ] = None,
    no_data_edges: Annotated[
        bool,
        typer.Option("--no-data-edges", help="Exclude data flow edges from Mermaid output"),
    ] = False,
    no_contains_edges: Annotated[
        bool,
        typer.Option("--no-contains-edges", help="Exclude parent-child (contains) edges from Mermaid output"),
    ] = False,
    data_flow: Annotated[
        bool,
        typer.Option("--data-flow", help="Generate data flow diagram instead of orchestration diagram"),
    ] = False,
    combo: Annotated[
        bool,
        typer.Option("--combo", help="Generate combo diagram (data flow with controller subgraphs)"),
    ] = False,
    reactflow: Annotated[
        bool,
        typer.Option("--reactflow", help="Also generate ReactFlow interactive HTML (.reactflow.html file)"),
    ] = False,
    reactflow_offline: Annotated[
        bool,
        typer.Option("--reactflow-offline", help="Use inline dependencies for ReactFlow (works offline, larger file)"),
    ] = False,
    reactflow_open: Annotated[
        bool,
        typer.Option("--reactflow-open", help="Open ReactFlow HTML in browser after generation"),
    ] = False,
) -> None:
    """Dry run a pipe and output its execution graph.

    By default, outputs JSON to stdout. Use --out to save to file(s).

    Examples:
        pipelex graph trace my_pipe
        pipelex graph trace my_pipe --out graph.json
        pipelex graph trace my_pipe --mermaid --html --out ./output/
        pipelex graph trace my_bundle.plx --mermaid --direction LR
        pipelex graph trace my_pipe --mermaid --data-flow  # Data lineage view
        pipelex graph trace my_pipe --mermaid --combo  # Combined view
    """
    # Handle deprecated --output flag
    if output and not out:
        out = output

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
            json_path, mermaid_path, html_path, reactflow_path = _resolve_output_paths(
                out=out,
                generate_json=generate_json,
                generate_mermaid=generate_mermaid,
                generate_html=generate_html,
                generate_reactflow=reactflow,
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
                graph_config = get_config().pipelex.pipeline_execution_config.graph_config
                if combo:
                    mermaid_output = graphspec_to_combo_mermaid(graph_spec, graph_config, direction=direction)
                    mermaid_code = mermaid_output.mermaid_code
                elif data_flow:
                    mermaid_output = graphspec_to_dataflow_mermaid(graph_spec, graph_config, direction=direction)
                    mermaid_code = mermaid_output.mermaid_code
                else:
                    mermaid_code = graphspec_to_orchestration_mermaid(
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

            # Generate and save ReactFlow HTML
            if reactflow and reactflow_path:
                # Determine title from pipe name
                title = pipe_code or bundle_path or "Pipelex Graph"
                if bundle_path:
                    title = Path(bundle_path).stem

                # Create ViewSpec from GraphSpec
                analysis = GraphAnalysis.from_graphspec(graph_spec)
                viewspec = graphspec_to_viewspec(graph_spec, analysis)

                # Generate ReactFlow HTML
                reactflow_html = generate_reactflow_html(
                    viewspec,
                    graphspec=graph_spec,
                    use_cdn=not reactflow_offline,
                    title=f"Graph: {title}",
                )
                reactflow_path.write_text(reactflow_html, encoding="utf-8")
                typer.secho(f"✅ ReactFlow HTML saved to: {reactflow_path}", fg=typer.colors.GREEN, err=True)

                # Open in browser if requested
                if reactflow_open:
                    webbrowser.open(f"file://{reactflow_path.absolute()}")
                    typer.secho("🌐 Opened ReactFlow HTML in browser", fg=typer.colors.BLUE, err=True)

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


@graph_app.command("render", help="Render an existing graph.json file to Mermaid combo.html and/or ReactFlow HTML")
def graph_render_cmd(
    input_file: Annotated[
        Path,
        typer.Argument(help="Path to an existing graph.json file"),
    ],
    out: Annotated[
        str | None,
        typer.Option("--out", "-o", help="Output directory (default: same directory as input)"),
    ] = None,
    direction: Annotated[
        FlowchartDirection | None,
        typer.Option("--direction", help="Flowchart direction (default: TB)"),
    ] = None,
    mermaid: Annotated[
        bool,
        typer.Option("--mermaid", "-m", help="Generate Mermaid combo.html only"),
    ] = False,
    reactflow: Annotated[
        bool,
        typer.Option("--reactflow", "-r", help="Generate ReactFlow reactflow.html only"),
    ] = False,
    all_views: Annotated[
        bool,
        typer.Option("--all", "-a", help="Generate all views: orchestration, dataflow, combo (Mermaid) + ReactFlow"),
    ] = False,
    open_browser: Annotated[
        bool,
        typer.Option("--open", help="Open the generated HTML in the default browser"),
    ] = False,
) -> None:
    """Render an existing graph.json file to HTML visualizations.

    By default generates both combo.html (Mermaid) and reactflow.html.
    Use --mermaid or --reactflow to generate only one of them.
    Use --all to generate all Mermaid views (orchestration, dataflow, combo) + ReactFlow.

    Examples:
        pipelex graph render graph.json                    # combo.html + reactflow.html
        pipelex graph render graph.json --mermaid          # combo.html only
        pipelex graph render graph.json --reactflow        # reactflow.html only
        pipelex graph render graph.json --all              # all views
        pipelex graph render graph.json --open             # open in browser
        pipelex graph render graph.json -o ./output/       # custom output directory
        pipelex graph render tests/data/graphs/cv_matching_graph.json --reactflow -o ./temp/test_outputs/ --open
    """
    # Validate input file exists
    if not input_file.exists():
        typer.secho(f"Error: File not found: {input_file}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    if input_file.suffix != ".json":
        typer.secho(f"Error: Expected .json file, got: {input_file}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    # Initialize Pipelex (needed for logging and other utilities)
    make_pipelex_for_cli(context=ErrorContext.VALIDATION)

    try:
        # Load the graph
        typer.echo(f"Loading graph from: {input_file}", err=True)
        graph_spec = load_graphspec(input_file)
        typer.secho(f"✅ Loaded graph with {len(graph_spec.nodes)} nodes", fg=typer.colors.GREEN, err=True)

        # Determine output directory
        output_dir: Path
        if out:
            output_dir = Path(out)
        else:
            output_dir = input_file.parent

        output_dir.mkdir(parents=True, exist_ok=True)

        # Determine what to generate:
        # - Default (no flags): combo.html + reactflow.html
        # - --mermaid: combo.html only
        # - --reactflow: reactflow.html only
        # - --all: orchestration, dataflow, combo + reactflow
        generate_mermaid_combo = (not mermaid and not reactflow and not all_views) or mermaid or all_views
        generate_reactflow = (not mermaid and not reactflow and not all_views) or reactflow or all_views
        generate_orchestration = all_views
        generate_dataflow = all_views

        generated_files: list[Path] = []

        async def render_views() -> None:
            """Inner async function to render views with async HTML generation."""
            nonlocal generated_files

            # Get graph config with data inclusion enabled for interactive views
            base_graph_config = get_config().pipelex.pipeline_execution_config.graph_config
            new_data_inclusion = base_graph_config.data_inclusion.model_copy(
                update={
                    "stuff_json_content": True,
                    "stuff_text_content": True,
                    "stuff_html_content": True,
                }
            )
            graph_config = base_graph_config.model_copy(update={"data_inclusion": new_data_inclusion})

            flow_direction = direction or FlowchartDirection.TOP_DOWN

            # Generate orchestration view (only with --all)
            if generate_orchestration:
                orch_mermaid = graphspec_to_orchestration_mermaid(graph_spec, direction=flow_direction)
                orch_html = await render_mermaid_html_async(orch_mermaid, title=f"Orchestration: {input_file.stem}")
                orch_html_path = output_dir / "orchestration.html"
                orch_html_path.write_text(orch_html, encoding="utf-8")
                generated_files.append(orch_html_path)
                typer.secho("✅ orchestration.html", fg=typer.colors.GREEN, err=True)

            # Generate dataflow view (only with --all)
            if generate_dataflow:
                dataflow_output = graphspec_to_dataflow_mermaid(graph_spec, graph_config, direction=flow_direction)
                if dataflow_output.stuff_data:
                    dataflow_html = await render_mermaid_html_with_data_async(
                        dataflow_output.mermaid_code,
                        stuff_data=dataflow_output.stuff_data,
                        stuff_data_text=dataflow_output.stuff_data_text,
                        stuff_data_html=dataflow_output.stuff_data_html,
                        stuff_metadata=dataflow_output.stuff_metadata,
                        title=f"Dataflow: {input_file.stem}",
                    )
                else:
                    dataflow_html = await render_mermaid_html_async(dataflow_output.mermaid_code, title=f"Dataflow: {input_file.stem}")
                dataflow_html_path = output_dir / "dataflow.html"
                dataflow_html_path.write_text(dataflow_html, encoding="utf-8")
                generated_files.append(dataflow_html_path)
                typer.secho("✅ dataflow.html", fg=typer.colors.GREEN, err=True)

            # Generate combo view (default + --mermaid + --all)
            if generate_mermaid_combo:
                combo_output = graphspec_to_combo_mermaid(graph_spec, graph_config, direction=flow_direction)
                if combo_output.stuff_data:
                    combo_html = await render_mermaid_html_with_data_async(
                        combo_output.mermaid_code,
                        stuff_data=combo_output.stuff_data,
                        stuff_data_text=combo_output.stuff_data_text,
                        stuff_data_html=combo_output.stuff_data_html,
                        stuff_metadata=combo_output.stuff_metadata,
                        title=f"Combo: {input_file.stem}",
                    )
                else:
                    combo_html = await render_mermaid_html_async(combo_output.mermaid_code, title=f"Combo: {input_file.stem}")
                combo_html_path = output_dir / "combo.html"
                combo_html_path.write_text(combo_html, encoding="utf-8")
                generated_files.append(combo_html_path)
                typer.secho("✅ combo.html", fg=typer.colors.GREEN, err=True)

            # Generate ReactFlow view (default + --reactflow + --all)
            if generate_reactflow:
                # Create ViewSpec from GraphSpec
                analysis = GraphAnalysis.from_graphspec(graph_spec)
                viewspec = graphspec_to_viewspec(graph_spec, analysis)

                # Collect stuff data in alternate formats
                rf_stuff_data_text = collect_stuff_data_text(graph_spec) if graph_config.data_inclusion.stuff_text_content else None
                rf_stuff_data_html = collect_stuff_data_html(graph_spec) if graph_config.data_inclusion.stuff_html_content else None

                # Generate ReactFlow HTML
                reactflow_html = await generate_reactflow_html_async(
                    viewspec,
                    graphspec=graph_spec,
                    stuff_data_text=rf_stuff_data_text,
                    stuff_data_html=rf_stuff_data_html,
                    title=f"ReactFlow: {input_file.stem}",
                )
                reactflow_path = output_dir / "reactflow.html"
                reactflow_path.write_text(reactflow_html, encoding="utf-8")
                generated_files.append(reactflow_path)
                typer.secho("✅ reactflow.html", fg=typer.colors.GREEN, err=True)

        asyncio.run(render_views())

        typer.secho(f"\n📊 Saved to: {output_dir}", fg=typer.colors.CYAN, bold=True, err=True)

        # Open in browser if requested
        if open_browser and generated_files:
            if len(generated_files) == 1:
                # Open the single generated file
                file_to_open = generated_files[0]
                webbrowser.open(f"file://{file_to_open.absolute()}")
                typer.secho(f"🌐 Opened {file_to_open.name} in browser", fg=typer.colors.BLUE, err=True)
            else:
                # Open the output directory so user can see all files
                webbrowser.open(f"file://{output_dir.absolute()}")
                typer.secho("🌐 Opened output directory in browser", fg=typer.colors.BLUE, err=True)

    except Exception as exc:
        log.error(f"Error rendering graph: {exc}")
        console = get_console()
        console.print("\n[bold red]Failed to render graph[/bold red]\n")
        console.print_exception(show_locals=True)
        raise typer.Exit(1) from exc

    finally:
        Pipelex.teardown_if_needed()
