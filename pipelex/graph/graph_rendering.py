"""Rendering a run graph to disk, from a spec that already exists.

Kernel-layer: everything here takes a :class:`GraphSpec` and turns it into files. Producing that
spec from a *bundle* needs a loaded method, so those helpers live one layer up, in
``pipelex.pipeline.bundle_graph_rendering``.
"""

from enum import StrEnum
from pathlib import Path

from pipelex.graph.graph_config import GraphConfig
from pipelex.graph.graph_factory import GraphOutputs, generate_graph_outputs, save_graph_outputs_to_dir
from pipelex.graph.graphspec import GraphSpec
from pipelex.tools.misc.chart_utils import FlowchartDirection


class GraphFormat(StrEnum):
    """Selectable graph output formats."""

    MERMAIDFLOW = "mermaidflow"
    REACTFLOW = "reactflow"
    BOTH = "both"


async def render_graph_from_spec(
    graph_spec: GraphSpec,
    *,
    graph_config: GraphConfig,
    include_mermaidflow: bool,
    include_reactflow: bool,
    output_dir: Path,
    pipe_code: str = "",
    title: str | None = None,
    direction: FlowchartDirection | None = None,
    include_subgraphs: bool = True,
) -> dict[str, Path]:
    """Render graph outputs from a graph spec and save to output_dir.

    Builds a render config from the provided graph config with format selection,
    generates graph outputs, and saves them to the output directory.

    Args:
        graph_spec: The graph spec produced by pipeline execution.
        graph_config: The base graph configuration.
        include_mermaidflow: Whether to generate Mermaid HTML output.
        include_reactflow: Whether to generate ReactFlow HTML output.
        output_dir: Directory where graph files will be saved.
        pipe_code: The pipe code, used to derive the HTML page title.
        title: Explicit title for the graph page (takes precedence over pipe_code).
        direction: Flowchart direction override.
        include_subgraphs: Whether to include controller subgraphs in Mermaid output.

    Returns:
        Dict mapping output format keys to saved file paths.
    """
    render_graph_config = graph_config.model_copy(
        update={
            "data_inclusion": graph_config.data_inclusion.model_copy(
                update={
                    "stuff_json_content": True,
                    "stuff_text_content": True,
                    "stuff_html_content": True,
                }
            ),
            "graphs_inclusion": graph_config.graphs_inclusion.model_copy(
                update={
                    "graphspec_json": False,
                    "mermaidflow_mmd": False,
                    "mermaidflow_html": include_mermaidflow,
                    "reactflow_html": include_reactflow,
                }
            ),
        }
    )

    graph_outputs: GraphOutputs = await generate_graph_outputs(
        graph_spec=graph_spec,
        graph_config=render_graph_config,
        pipe_code=pipe_code,
        title=title,
        direction=direction,
        include_subgraphs=include_subgraphs,
    )

    return save_graph_outputs_to_dir(graph_outputs=graph_outputs, output_dir=output_dir)
