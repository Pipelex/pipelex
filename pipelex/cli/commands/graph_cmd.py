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
from posthog import tag

from pipelex import log
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import ErrorContext
from pipelex.config import get_config
from pipelex.graph.graph_rendering import render_graph_from_spec
from pipelex.graph.graphspec import GraphSpec
from pipelex.pipelex import Pipelex
from pipelex.runtime_hub import get_console, get_telemetry_manager
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventName, EventProperty
from pipelex.tools.misc.chart_utils import FlowchartDirection
from pipelex.tools.misc.file_utils import load_text_from_path
from pipelex.tools.misc.package_utils import get_package_version
from pipelex.tools.misc.string_utils import snake_to_title_case

COMMAND = "graph"

graph_app = typer.Typer(no_args_is_help=True)


def _do_graph_render(
    input_file: Path,
    *,
    out: str | None,
    direction: FlowchartDirection | None,
    mermaidflow: bool,
    reactflow: bool,
    subgraphs: bool,
    open_browser: bool,
) -> None:
    """Execute the graph render logic."""
    get_telemetry_manager().track_event(EventName.GRAPH_RENDER)
    # Load the graph
    typer.echo(f"Loading graph from: {input_file}", err=True)
    json_str = load_text_from_path(input_file)
    graph_spec = GraphSpec.model_validate_json(json_str)
    typer.secho(f"✅ Loaded graph with {len(graph_spec.nodes)} nodes", fg=typer.colors.GREEN, err=True)

    # Determine output directory
    output_dir: Path
    if out:
        output_dir = Path(out)
    else:
        output_dir = input_file.parent

    # Determine what to generate:
    # - Default (no flags): both mermaidflow.html + reactflow.html
    # - --mermaidflow: mermaidflow.html only
    # - --reactflow: reactflow.html only
    include_mermaidflow = mermaidflow or (not mermaidflow and not reactflow)
    include_reactflow = reactflow or (not mermaidflow and not reactflow)

    base_graph_config = get_config().pipelex.pipeline_execution_config.graph_config
    flow_direction = direction or FlowchartDirection.TOP_DOWN

    saved_files = asyncio.run(
        render_graph_from_spec(
            graph_spec=graph_spec,
            graph_config=base_graph_config,
            include_mermaidflow=include_mermaidflow,
            include_reactflow=include_reactflow,
            output_dir=output_dir,
            title=snake_to_title_case(input_file.stem),
            direction=flow_direction,
            include_subgraphs=subgraphs,
        )
    )

    # Report saved files
    for file_path in saved_files.values():
        typer.secho(f"✅ {file_path.name}", fg=typer.colors.GREEN, err=True)

    typer.secho(f"\n📊 Saved to: {output_dir}", fg=typer.colors.CYAN, bold=True, err=True)

    # Open in browser if requested
    if open_browser and saved_files:
        saved_paths = list(saved_files.values())
        if len(saved_paths) == 1:
            file_to_open = saved_paths[0]
            webbrowser.open(f"file://{file_to_open.absolute()}")
            typer.secho(f"🌐 Opened {file_to_open.name} in browser", fg=typer.colors.BLUE, err=True)
        else:
            webbrowser.open(f"file://{output_dir.absolute()}")
            typer.secho("🌐 Opened output directory in browser", fg=typer.colors.BLUE, err=True)


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
        typer.Option("--direction", help="Flowchart direction"),
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
    make_pipelex_for_cli(context=ErrorContext.VALIDATION, needs_inference=False)

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
            tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} render")
            _do_graph_render(
                input_file=input_file,
                out=out,
                direction=direction,
                mermaidflow=mermaidflow,
                reactflow=reactflow,
                subgraphs=subgraphs,
                open_browser=open_browser,
            )

    except Exception as exc:
        # CLI command root: any unexpected failure is reported to the user and exits non-zero via typer.Exit.
        log.error(f"Error rendering graph: {exc}")
        console = get_console()
        console.print("\n[bold red]Failed to render graph[/bold red]\n")
        console.print_exception(show_locals=True)
        raise typer.Exit(1) from exc

    finally:
        Pipelex.teardown_if_needed()
