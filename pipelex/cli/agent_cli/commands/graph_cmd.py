"""Agent CLI graph command - render graphspec.json to HTML visualizations with JSON output."""

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import ErrorContext
from pipelex.config import get_config
from pipelex.graph.graph_factory import generate_graph_outputs
from pipelex.graph.graphspec import GraphSpec
from pipelex.pipelex import Pipelex
from pipelex.tools.misc.file_utils import load_text_from_path
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

    output_dir.mkdir(parents=True, exist_ok=True)

    # Initialize Pipelex (needed for config access)
    make_pipelex_for_cli(context=ErrorContext.VALIDATION)

    try:
        # Build graph config with data inclusion and format selection
        base_graph_config = get_config().pipelex.pipeline_execution_config.graph_config
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

        # Derive a pipe code from the graphspec file name for the HTML title
        pipe_code = input_path.stem.replace("graphspec", "").strip("_.- ")
        if not pipe_code:
            pipe_code = "pipeline"

        graph_outputs = asyncio.run(
            generate_graph_outputs(
                graph_spec=graph_spec,
                graph_config=graph_config,
                pipe_code=pipe_code,
            )
        )

        # Save generated files
        files: dict[str, str] = {}

        if graph_outputs.mermaidflow_html is not None:
            mermaidflow_path = output_dir / "mermaidflow.html"
            mermaidflow_path.write_text(graph_outputs.mermaidflow_html, encoding="utf-8")
            files["mermaidflow_html"] = str(mermaidflow_path)

        if graph_outputs.reactflow_html is not None:
            reactflow_path = output_dir / "reactflow.html"
            reactflow_path.write_text(graph_outputs.reactflow_html, encoding="utf-8")
            files["reactflow_html"] = str(reactflow_path)

        agent_success(
            {
                "success": True,
                "output_dir": str(output_dir),
                "files": files,
                "node_count": len(graph_spec.nodes),
            }
        )

    except Exception as exc:
        agent_error(f"Failed to render graph: {exc}", type(exc).__name__, cause=exc)

    finally:
        Pipelex.teardown_if_needed()
