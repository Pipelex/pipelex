"""CLI commands to render execution graphs."""

from __future__ import annotations

import asyncio
import webbrowser
from pathlib import Path
from typing import Annotated

import typer

from pipelex import log
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import ErrorContext
from pipelex.config import get_config
from pipelex.graph.graph_analysis import GraphAnalysis
from pipelex.graph.graphspec_io import load_graphspec
from pipelex.graph.mermaid import (
    collect_stuff_data_html,
    collect_stuff_data_text,
    graphspec_to_combo_mermaid,
    graphspec_to_dataflow_mermaid,
    graphspec_to_orchestration_mermaid,
)
from pipelex.graph.mermaid_html import render_mermaid_html_async, render_mermaid_html_with_data_async
from pipelex.graph.reactflow_html import generate_reactflow_html_async
from pipelex.graph.viewspec_transformer import graphspec_to_viewspec
from pipelex.hub import get_console
from pipelex.pipelex import Pipelex
from pipelex.tools.misc.chart_utils import FlowchartDirection

graph_app = typer.Typer(no_args_is_help=True)


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
    data_edges: Annotated[
        bool,
        typer.Option("--data-edges/--no-data-edges", help="Include data flow edges in orchestration Mermaid output"),
    ] = True,
    contains_edges: Annotated[
        bool,
        typer.Option("--contains-edges/--no-contains-edges", help="Include parent-child (contains) edges in orchestration Mermaid output"),
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
        pipelex graph render graph.json --all --no-data-edges   # all views without data edges
        pipelex graph render graph.json --open             # open in browser
        pipelex graph render graph.json -o ./output/       # custom output directory
        pipelex graph render tests/data/graphs/cv_matching_graph.json --reactflow -o ./temp/test_outputs/
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
                orch_mermaid = graphspec_to_orchestration_mermaid(
                    graph_spec,
                    direction=flow_direction,
                    include_data_edges=data_edges,
                    include_contains_edges=contains_edges,
                )
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
                    graph_config.reactflow_config,
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
