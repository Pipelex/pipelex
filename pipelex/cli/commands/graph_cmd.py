"""CLI commands to render execution graphs.

Supports two graph view types:
- mermaidflow: Mermaid-based flowchart visualization
- reactflow: ReactFlow interactive visualization
"""

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
from pipelex.graph.graphspec import GraphSpec
from pipelex.graph.mermaidflow.mermaid_html import render_mermaid_html_async, render_mermaid_html_with_data_async
from pipelex.graph.mermaidflow.mermaidflow_factory import MermaidflowFactory
from pipelex.graph.mermaidflow.stuff_collector import collect_stuff_data_html, collect_stuff_data_text
from pipelex.graph.reactflow.reactflow_html import generate_reactflow_html_async
from pipelex.graph.reactflow.viewspec_transformer import graphspec_to_viewspec
from pipelex.hub import get_console
from pipelex.pipelex import Pipelex
from pipelex.tools.misc.chart_utils import FlowchartDirection
from pipelex.tools.misc.file_utils import load_text_from_path
from pipelex.tools.misc.string_utils import snake_to_title_case

graph_app = typer.Typer(no_args_is_help=True)


@graph_app.command("render", help="Render an existing graph.json file to mermaidflow.html and/or reactflow.html")
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
    mermaidflow: Annotated[
        bool,
        typer.Option("--mermaidflow", "-m", help="Generate mermaidflow.html only"),
    ] = False,
    reactflow: Annotated[
        bool,
        typer.Option("--reactflow", "-r", help="Generate reactflow.html only"),
    ] = False,
    subgraphs: Annotated[
        bool,
        typer.Option("--subgraphs/--no-subgraphs", help="Include controller subgraphs in mermaidflow output"),
    ] = True,
    open_browser: Annotated[
        bool,
        typer.Option("--open", help="Open the generated HTML in the default browser"),
    ] = False,
) -> None:
    """Render an existing graph.json file to HTML visualizations.

    By default generates both mermaidflow.html (Mermaid) and reactflow.html (ReactFlow).
    Use --mermaidflow or --reactflow to generate only one of them.

    Examples:
        pipelex graph render graph.json                        # both mermaidflow.html + reactflow.html
        pipelex graph render graph.json --mermaidflow          # mermaidflow.html only
        pipelex graph render graph.json --reactflow            # reactflow.html only
        pipelex graph render graph.json --mermaidflow --no-subgraphs  # flat mermaidflow (no hierarchy)
        pipelex graph render graph.json --open                 # open in browser
        pipelex graph render graph.json -o ./output/           # custom output directory
        pipelex graph render tests/data/graphs/cv_job_match.json -o ./temp/test_outputs/
        pipelex graph render tests/data/graphs/cv_job_match.json --reactflow -o ./temp/test_outputs/
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
        json_str = load_text_from_path(str(input_file))
        graph_spec = GraphSpec.model_validate_json(json_str)
        typer.secho(f"✅ Loaded graph with {len(graph_spec.nodes)} nodes", fg=typer.colors.GREEN, err=True)

        # Determine output directory
        output_dir: Path
        if out:
            output_dir = Path(out)
        else:
            output_dir = input_file.parent

        output_dir.mkdir(parents=True, exist_ok=True)

        # Determine what to generate:
        # - Default (no flags): both mermaidflow.html + reactflow.html
        # - --mermaidflow: mermaidflow.html only
        # - --reactflow: reactflow.html only
        generate_mermaidflow = mermaidflow or (not mermaidflow and not reactflow)
        generate_reactflow = reactflow or (not mermaidflow and not reactflow)

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

            # Get the mermaid theme from config
            mermaid_theme = graph_config.mermaid_config.style.theme

            flow_direction = direction or FlowchartDirection.TOP_DOWN

            # Generate mermaidflow view (default + --mermaidflow)
            if generate_mermaidflow:
                the_mermaidflow = MermaidflowFactory.make_from_graphspec(
                    graph_spec,
                    graph_config,
                    direction=flow_direction,
                    include_subgraphs=subgraphs,
                )
                if the_mermaidflow.stuff_data:
                    mermaidflow_html = await render_mermaid_html_with_data_async(
                        the_mermaidflow.mermaid_code,
                        stuff_data=the_mermaidflow.stuff_data,
                        stuff_data_text=the_mermaidflow.stuff_data_text,
                        stuff_data_html=the_mermaidflow.stuff_data_html,
                        stuff_metadata=the_mermaidflow.stuff_metadata,
                        stuff_content_type=the_mermaidflow.stuff_content_type,
                        title=f"Pipeline: {snake_to_title_case(input_file.stem)}",
                        theme=mermaid_theme,
                    )
                else:
                    mermaidflow_html = await render_mermaid_html_async(
                        the_mermaidflow.mermaid_code,
                        title=f"Pipeline: {snake_to_title_case(input_file.stem)}",
                        theme=mermaid_theme,
                    )
                mermaidflow_html_path = output_dir / "mermaidflow.html"
                mermaidflow_html_path.write_text(mermaidflow_html, encoding="utf-8")
                generated_files.append(mermaidflow_html_path)
                typer.secho("✅ mermaidflow.html", fg=typer.colors.GREEN, err=True)

            # Generate ReactFlow view (default + --reactflow)
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
                    title=f"Pipeline: {snake_to_title_case(input_file.stem)}",
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
