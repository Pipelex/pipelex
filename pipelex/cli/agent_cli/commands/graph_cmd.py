"""Agent CLI graph command - render graphspec.json to HTML visualizations with JSON output."""

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success
from pipelex.config import get_config
from pipelex.graph.graph_factory import generate_graph_outputs, save_graph_outputs_to_dir
from pipelex.graph.graphspec import GraphSpec
from pipelex.pipelex import Pipelex
from pipelex.tools.misc.file_utils import load_text_from_path
from pipelex.tools.misc.string_utils import snake_to_title_case
from pipelex.types import StrEnum


class GraphFormat(StrEnum):
    """Selectable graph output formats."""

    MERMAIDFLOW = "mermaidflow"
    REACTFLOW = "reactflow"
    BOTH = "both"


def graph_cmd(
    graphspec_file: Annotated[
        str,
        typer.Argument(help="Path to a graphspec.json file"),
    ],
    out: Annotated[
        str | None,
        typer.Option("--out", "-o", help="Output directory (default: same directory as input file)"),
    ] = None,
    graph_format: Annotated[
        GraphFormat,
        typer.Option("--format", "-f", help="Graph format to generate: mermaidflow, reactflow, or both"),
    ] = GraphFormat.BOTH,
) -> None:
    """Render a graphspec.json file to HTML visualizations.

    Outputs JSON to stdout on success, JSON to stderr on error with exit code 1.

    Examples:
        pipelex-agent graph graphspec.json
        pipelex-agent graph graphspec.json --format mermaidflow
        pipelex-agent graph graphspec.json -o ./output/ --format reactflow
    """
    input_path = Path(graphspec_file)

    if not input_path.exists():
        agent_error(f"File not found: {graphspec_file}", "FileNotFoundError")

    if input_path.suffix != ".json":
        agent_error(f"Expected .json file, got: {input_path.name}", "ArgumentError")

    # Load and parse the GraphSpec
    try:
        json_str = load_text_from_path(str(input_path))
    except Exception as exc:
        agent_error(f"Failed to read file: {exc}", type(exc).__name__, cause=exc)

    try:
        graph_spec = GraphSpec.model_validate_json(json_str)
    except Exception as exc:
        agent_error(f"Invalid graphspec JSON: {exc}", "GraphSpecParseError", cause=exc)

    # Determine output directory
    output_dir: Path
    if out:
        output_dir = Path(out)
    else:
        output_dir = input_path.parent

    # Initialize Pipelex (needed for config access)
    make_pipelex_for_agent_cli()

    try:
        base_graph_config = get_config().pipelex.pipeline_execution_config.graph_config

        # Enable all content formats (JSON, text, HTML) so the interactive HTML
        # viewers can display data panels alongside the graph visualization
        new_data_inclusion = base_graph_config.data_inclusion.model_copy(
            update={
                "stuff_json_content": True,
                "stuff_text_content": True,
                "stuff_html_content": True,
            }
        )

        include_mermaidflow: bool
        include_reactflow: bool
        match graph_format:
            case GraphFormat.MERMAIDFLOW:
                include_mermaidflow = True
                include_reactflow = False
            case GraphFormat.REACTFLOW:
                include_mermaidflow = False
                include_reactflow = True
            case GraphFormat.BOTH:
                include_mermaidflow = True
                include_reactflow = True

        # Only generate the final HTML files requested — skip intermediate formats
        # (graphspec JSON, Mermaid .mmd source, ReactFlow viewspec JSON) that are
        # only useful during pipeline execution, not for standalone rendering
        new_graphs_inclusion = base_graph_config.graphs_inclusion.model_copy(
            update={
                "graphspec_json": False,
                "mermaidflow_mmd": False,
                "mermaidflow_html": include_mermaidflow,
                "reactflow_viewspec": False,
                "reactflow_html": include_reactflow,
            }
        )

        graph_config = base_graph_config.model_copy(
            update={
                "data_inclusion": new_data_inclusion,
                "graphs_inclusion": new_graphs_inclusion,
            }
        )

        graph_outputs = asyncio.run(
            generate_graph_outputs(
                graph_spec=graph_spec,
                graph_config=graph_config,
                title=snake_to_title_case(input_path.stem),
            )
        )

        # Save generated files
        saved_files = save_graph_outputs_to_dir(graph_outputs=graph_outputs, output_dir=output_dir)

        agent_success(
            {
                "success": True,
                "output_dir": str(output_dir),
                "files": {key: str(path) for key, path in saved_files.items()},
                "node_count": len(graph_spec.nodes),
            }
        )

    except Exception as exc:
        agent_error(f"Failed to render graph: {exc}", type(exc).__name__, cause=exc)

    finally:
        Pipelex.teardown_if_needed()
