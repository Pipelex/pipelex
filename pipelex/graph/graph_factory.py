"""Graph output factory for generating graph content.

This module provides factory functions for generating graph outputs including
JSON, Mermaid (mermaidflow), ReactFlow, and HTML content.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from pipelex import log
from pipelex.graph.mermaidflow.mermaid_html import render_mermaid_html_async, render_mermaid_html_with_data_async
from pipelex.graph.mermaidflow.mermaidflow_factory import MermaidflowFactory
from pipelex.graph.mermaidflow.stuff_collector import collect_stuff_data_html, collect_stuff_data_text
from pipelex.graph.reactflow.reactflow_html import generate_reactflow_html_async
from pipelex.tools.misc.string_utils import snake_to_title_case

if TYPE_CHECKING:
    from pathlib import Path

    from pipelex.graph.graph_config import GraphConfig
    from pipelex.graph.graphspec import GraphSpec
    from pipelex.tools.misc.chart_utils import FlowchartDirection


class GraphOutputs(BaseModel):
    """Container for generated graph output content.

    All fields are optional - only included outputs will be populated based on GraphConfig.graphs_inclusion.

    Attributes:
        graphspec_json: The GraphSpec serialized as JSON.
        mermaidflow_mmd: Mermaidflow view as Mermaid flowchart code.
        mermaidflow_html: Mermaidflow view as standalone HTML page.
        reactflow_html: ReactFlow interactive graph as standalone HTML page.
    """

    graphspec_json: str | None = None
    mermaidflow_mmd: str | None = None
    mermaidflow_html: str | None = None
    reactflow_html: str | None = None


async def generate_graph_outputs(
    graph_spec: GraphSpec,
    graph_config: GraphConfig,
    *,
    pipe_code: str = "",
    title: str | None = None,
    direction: FlowchartDirection | None = None,
    include_subgraphs: bool = True,
) -> GraphOutputs:
    """Generate graph outputs from a GraphSpec based on configuration.

    Only outputs enabled in graph_config.graphs_inclusion will be generated.

    This can generate:
    - GraphSpec JSON: The canonical graph representation
    - Mermaidflow view: Data flow with controller subgraphs (Mermaid)
    - ReactFlow HTML: Interactive graph viewer

    Args:
        graph_spec: The GraphSpec to render.
        graph_config: Configuration controlling which outputs to generate and data inclusion.
        pipe_code: The pipe code, used to derive the HTML page title when title is not provided.
        title: Explicit HTML page title. When provided, overrides the auto-derived title from pipe_code.
        direction: Flowchart direction override for both Mermaid and ReactFlow outputs. When None, each renderer uses its own config default.
        include_subgraphs: Whether to render controller hierarchy as subgraphs in Mermaid output.

    Returns:
        GraphOutputs containing generated content as strings (None for disabled outputs).
    """
    page_title = title or f"Pipeline: {snake_to_title_case(pipe_code)}"
    inclusion = graph_config.graphs_inclusion

    graphspec_json: str | None = None
    mermaidflow_mmd: str | None = None
    mermaidflow_html: str | None = None
    reactflow_html: str | None = None

    # Generate GraphSpec JSON
    if inclusion.graphspec_json:
        # graphspec_json = graph_spec.model_dump_json(indent=2, by_alias=True)
        graphspec_json = graph_spec.to_json()

    # Get the mermaid theme from config
    mermaid_theme = graph_config.mermaid_config.style.theme

    # Resolve mermaid direction: explicit override takes priority, then config
    effective_direction = direction or graph_config.mermaid_config.direction

    # Generate mermaidflow view
    if inclusion.mermaidflow_mmd or inclusion.mermaidflow_html:
        mermaidflow = MermaidflowFactory.make_from_graphspec(
            graph_spec, graph_config, direction=effective_direction, include_subgraphs=include_subgraphs
        )
        if inclusion.mermaidflow_mmd:
            mermaidflow_mmd = mermaidflow.mermaid_code
        if inclusion.mermaidflow_html:
            has_any_stuff_data = mermaidflow.stuff_data or mermaidflow.stuff_data_text or mermaidflow.stuff_data_html
            if has_any_stuff_data:
                mermaidflow_html = await render_mermaid_html_with_data_async(
                    mermaidflow.mermaid_code,
                    stuff_data=mermaidflow.stuff_data,
                    stuff_data_text=mermaidflow.stuff_data_text,
                    stuff_data_html=mermaidflow.stuff_data_html,
                    stuff_metadata=mermaidflow.stuff_metadata,
                    stuff_content_type=mermaidflow.stuff_content_type,
                    title=page_title,
                    theme=mermaid_theme,
                )
            else:
                mermaidflow_html = await render_mermaid_html_async(mermaidflow.mermaid_code, title=page_title, theme=mermaid_theme)

    # Generate ReactFlow HTML
    if inclusion.reactflow_html:
        # Collect stuff data in alternate formats if configured
        rf_stuff_data_text: dict[str, str] | None = None
        rf_stuff_data_html: dict[str, str] | None = None
        if graph_config.data_inclusion.stuff_text_content:
            log.verbose("Collecting stuff data text for graph_spec")
            rf_stuff_data_text = collect_stuff_data_text(graph_spec)
        else:
            log.verbose("No stuff data text to collect for graph_spec")
        if graph_config.data_inclusion.stuff_html_content:
            rf_stuff_data_html = collect_stuff_data_html(graph_spec)

        effective_rf_config = graph_config.reactflow_config
        if direction is not None:
            effective_rf_config = effective_rf_config.model_copy(update={"layout_direction": direction})
        reactflow_html = await generate_reactflow_html_async(
            graph_spec,
            effective_rf_config,
            stuff_data_text=rf_stuff_data_text,
            stuff_data_html=rf_stuff_data_html,
            title=page_title,
        )

    return GraphOutputs(
        graphspec_json=graphspec_json,
        mermaidflow_mmd=mermaidflow_mmd,
        mermaidflow_html=mermaidflow_html,
        reactflow_html=reactflow_html,
    )


def save_graph_outputs_to_dir(
    graph_outputs: GraphOutputs,
    output_dir: Path,
) -> dict[str, Path]:
    """Save graph outputs to a directory.

    Only outputs that are not None will be saved. Each output is written to a
    standard filename within the output directory.

    Args:
        graph_outputs: The generated graph outputs to save.
        output_dir: Directory where graph files will be saved (created if needed).

    Returns:
        Dictionary mapping output type keys to the saved file paths.
        Keys match GraphOutputs field names (e.g. "graphspec_json", "mermaidflow_html").
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_files: dict[str, Path] = {}

    if graph_outputs.graphspec_json is not None:
        file_path = output_dir / "graphspec.json"
        file_path.write_text(graph_outputs.graphspec_json, encoding="utf-8")
        saved_files["graphspec_json"] = file_path
        log.verbose(f"GraphSpec JSON saved to: {file_path}")

    if graph_outputs.mermaidflow_mmd is not None:
        file_path = output_dir / "mermaidflow.mmd"
        file_path.write_text(graph_outputs.mermaidflow_mmd, encoding="utf-8")
        saved_files["mermaidflow_mmd"] = file_path
        log.verbose(f"Mermaidflow MMD saved to: {file_path}")

    if graph_outputs.mermaidflow_html is not None:
        file_path = output_dir / "mermaidflow.html"
        file_path.write_text(graph_outputs.mermaidflow_html, encoding="utf-8")
        saved_files["mermaidflow_html"] = file_path
        log.verbose(f"Mermaidflow HTML saved to: {file_path}")

    if graph_outputs.reactflow_html is not None:
        file_path = output_dir / "reactflow.html"
        file_path.write_text(graph_outputs.reactflow_html, encoding="utf-8")
        saved_files["reactflow_html"] = file_path
        log.verbose(f"ReactFlow HTML saved to: {file_path}")

    return saved_files
