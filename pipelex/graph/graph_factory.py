"""Graph output factory for generating graph content.

This module provides factory functions for generating graph outputs including
JSON, Mermaid (mermaidflow), ReactFlow, and HTML content.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from pipelex import log
from pipelex.graph.graph_analysis import GraphAnalysis
from pipelex.graph.mermaidflow.mermaid_html import render_mermaid_html_async, render_mermaid_html_with_data_async
from pipelex.graph.mermaidflow.mermaidflow_factory import MermaidflowFactory
from pipelex.graph.mermaidflow.stuff_collector import collect_stuff_data_html, collect_stuff_data_text
from pipelex.graph.reactflow.reactflow_html import generate_reactflow_html_async
from pipelex.graph.reactflow.viewspec_transformer import graphspec_to_viewspec
from pipelex.tools.misc.chart_utils import FlowchartDirection
from pipelex.tools.misc.string_utils import snake_to_title_case

if TYPE_CHECKING:
    from pipelex.graph.graph_config import GraphConfig
    from pipelex.graph.graphspec import GraphSpec


class GraphOutputs(BaseModel):
    """Container for generated graph output content.

    All fields are optional - only included outputs will be populated based on GraphConfig.graphs_inclusion.

    Attributes:
        graphspec_json: The GraphSpec serialized as JSON.
        mermaidflow_mmd: Mermaidflow view as Mermaid flowchart code.
        mermaidflow_html: Mermaidflow view as standalone HTML page.
        reactflow_viewspec: The ViewSpec serialized as JSON for ReactFlow rendering.
        reactflow_html: ReactFlow interactive graph as standalone HTML page.
    """

    graphspec_json: str | None = None
    mermaidflow_mmd: str | None = None
    mermaidflow_html: str | None = None
    reactflow_viewspec: str | None = None
    reactflow_html: str | None = None


async def generate_graph_outputs(
    graph_spec: GraphSpec,
    graph_config: GraphConfig,
    pipe_code: str,
    *,
    direction: FlowchartDirection = FlowchartDirection.TOP_DOWN,
) -> GraphOutputs:
    """Generate graph outputs from a GraphSpec based on configuration.

    Only outputs enabled in graph_config.graphs_inclusion will be generated.

    This can generate:
    - GraphSpec JSON: The canonical graph representation
    - Mermaidflow view: Data flow with controller subgraphs (Mermaid)
    - ReactFlow ViewSpec: JSON for ReactFlow rendering
    - ReactFlow HTML: Interactive graph viewer

    Args:
        graph_spec: The GraphSpec to render.
        graph_config: Configuration controlling which outputs to generate and data inclusion.
        pipe_code: The pipe code for use in titles.
        direction: Flowchart direction for Mermaid diagrams.

    Returns:
        GraphOutputs containing generated content as strings (None for disabled outputs).
    """
    inclusion = graph_config.graphs_inclusion

    graphspec_json: str | None = None
    mermaidflow_mmd: str | None = None
    mermaidflow_html: str | None = None
    reactflow_viewspec: str | None = None
    reactflow_html: str | None = None

    # Generate GraphSpec JSON
    if inclusion.graphspec_json:
        # graphspec_json = graph_spec.model_dump_json(indent=2, by_alias=True)
        graphspec_json = graph_spec.to_json()

    # Get the mermaid theme from config
    mermaid_theme = graph_config.mermaid_config.style.theme

    # Generate mermaidflow view
    if inclusion.mermaidflow_mmd or inclusion.mermaidflow_html:
        mermaidflow = MermaidflowFactory.make_from_graphspec(graph_spec, graph_config, direction=direction)
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
                    title=f"Pipeline: {snake_to_title_case(pipe_code)}",
                    theme=mermaid_theme,
                )
            else:
                mermaidflow_html = await render_mermaid_html_async(
                    mermaidflow.mermaid_code, title=f"Pipeline: {snake_to_title_case(pipe_code)}", theme=mermaid_theme
                )

    # Generate ReactFlow outputs
    if inclusion.reactflow_viewspec or inclusion.reactflow_html:
        analysis = GraphAnalysis.from_graphspec(graph_spec)
        viewspec = graphspec_to_viewspec(graph_spec, analysis)

        if inclusion.reactflow_viewspec:
            reactflow_viewspec = viewspec.model_dump_json(indent=2)

        if inclusion.reactflow_html:
            # Collect stuff data in alternate formats if configured
            rf_stuff_data_text: dict[str, str] | None = None
            rf_stuff_data_html: dict[str, str] | None = None
            if graph_config.data_inclusion.stuff_text_content:
                log.debug("collecting stuff data text for graph_spec")
                rf_stuff_data_text = collect_stuff_data_text(graph_spec)
            else:
                log.debug("no stuff data text to collect for graph_spec")
            if graph_config.data_inclusion.stuff_html_content:
                rf_stuff_data_html = collect_stuff_data_html(graph_spec)

            reactflow_html = await generate_reactflow_html_async(
                viewspec,
                graph_config.reactflow_config,
                graphspec=graph_spec,
                stuff_data_text=rf_stuff_data_text,
                stuff_data_html=rf_stuff_data_html,
                title=f"Pipeline: {snake_to_title_case(pipe_code)}",
            )

    return GraphOutputs(
        graphspec_json=graphspec_json,
        mermaidflow_mmd=mermaidflow_mmd,
        mermaidflow_html=mermaidflow_html,
        reactflow_viewspec=reactflow_viewspec,
        reactflow_html=reactflow_html,
    )
