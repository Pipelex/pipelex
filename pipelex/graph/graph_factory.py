"""Graph output factory for generating graph content.

This module provides factory functions for generating graph outputs including
JSON, Mermaid, ReactFlow, and HTML content for orchestration, data flow, and combo views.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from pipelex import log
from pipelex.graph.graph_analysis import GraphAnalysis
from pipelex.graph.graphspec_io import graphspec_to_json
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
from pipelex.tools.misc.chart_utils import FlowchartDirection

if TYPE_CHECKING:
    from pipelex.graph.graph_config import GraphConfig
    from pipelex.graph.graphspec import GraphSpec


class GraphOutputs(BaseModel):
    """Container for generated graph output content.

    All fields are optional - only included outputs will be populated based on GraphConfig.graphs_inclusion.

    Attributes:
        graphspec_json: The GraphSpec serialized as JSON.
        orchestration_mmd: Orchestration view as Mermaid flowchart code.
        orchestration_html: Orchestration view as standalone HTML page.
        dataflow_mmd: Data flow view as Mermaid flowchart code.
        dataflow_html: Data flow view as standalone HTML page.
        combo_mmd: Combo view as Mermaid flowchart code.
        combo_html: Combo view as standalone HTML page.
        reactflow_viewspec: The ViewSpec serialized as JSON for ReactFlow rendering.
        reactflow_html: ReactFlow interactive graph as standalone HTML page.
    """

    graphspec_json: str | None = None
    orchestration_mmd: str | None = None
    orchestration_html: str | None = None
    dataflow_mmd: str | None = None
    dataflow_html: str | None = None
    combo_mmd: str | None = None
    combo_html: str | None = None
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
    - Orchestration view: Shows control flow and controller containment (Mermaid)
    - Data flow view: Shows how data flows between pipes (Mermaid)
    - Combo view: Combined data flow with controller subgraphs (Mermaid)
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
    orchestration_mmd: str | None = None
    orchestration_html: str | None = None
    dataflow_mmd: str | None = None
    dataflow_html: str | None = None
    combo_mmd: str | None = None
    combo_html: str | None = None
    reactflow_viewspec: str | None = None
    reactflow_html: str | None = None

    # Generate GraphSpec JSON
    if inclusion.graphspec_json:
        graphspec_json = graphspec_to_json(graph_spec)

    # Get the mermaid theme from config
    mermaid_theme = graph_config.mermaid_config.style.theme

    # Generate orchestration view
    if inclusion.orchestration_mmd:
        orchestration_mmd = graphspec_to_orchestration_mermaid(graph_spec, direction=direction)

    if inclusion.orchestration_html:
        # Need the mermaid code to generate HTML
        mmd_for_html = orchestration_mmd or graphspec_to_orchestration_mermaid(graph_spec, direction=direction)
        orchestration_html = await render_mermaid_html_async(mmd_for_html, title=f"Orchestration: {pipe_code}", theme=mermaid_theme)

    # Generate data flow view
    if inclusion.dataflow_mmd or inclusion.dataflow_html:
        dataflow_output = graphspec_to_dataflow_mermaid(graph_spec, graph_config, direction=direction)
        if inclusion.dataflow_mmd:
            dataflow_mmd = dataflow_output.mermaid_code
        if inclusion.dataflow_html:
            has_any_stuff_data = dataflow_output.stuff_data or dataflow_output.stuff_data_text or dataflow_output.stuff_data_html
            if has_any_stuff_data:
                dataflow_html = await render_mermaid_html_with_data_async(
                    dataflow_output.mermaid_code,
                    stuff_data=dataflow_output.stuff_data,
                    stuff_data_text=dataflow_output.stuff_data_text,
                    stuff_data_html=dataflow_output.stuff_data_html,
                    stuff_metadata=dataflow_output.stuff_metadata,
                    title=f"Data Flow: {pipe_code}",
                    theme=mermaid_theme,
                )
            else:
                dataflow_html = await render_mermaid_html_async(dataflow_output.mermaid_code, title=f"Data Flow: {pipe_code}", theme=mermaid_theme)

    # Generate combo view
    if inclusion.combo_mmd or inclusion.combo_html:
        combo_output = graphspec_to_combo_mermaid(graph_spec, graph_config, direction=direction)
        if inclusion.combo_mmd:
            combo_mmd = combo_output.mermaid_code
        if inclusion.combo_html:
            has_any_stuff_data = combo_output.stuff_data or combo_output.stuff_data_text or combo_output.stuff_data_html
            if has_any_stuff_data:
                combo_html = await render_mermaid_html_with_data_async(
                    combo_output.mermaid_code,
                    stuff_data=combo_output.stuff_data,
                    stuff_data_text=combo_output.stuff_data_text,
                    stuff_data_html=combo_output.stuff_data_html,
                    stuff_metadata=combo_output.stuff_metadata,
                    title=f"Combo: {pipe_code}",
                    theme=mermaid_theme,
                )
            else:
                combo_html = await render_mermaid_html_async(combo_output.mermaid_code, title=f"Combo: {pipe_code}", theme=mermaid_theme)

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
                title=f"ReactFlow: {pipe_code}",
            )

    return GraphOutputs(
        graphspec_json=graphspec_json,
        orchestration_mmd=orchestration_mmd,
        orchestration_html=orchestration_html,
        dataflow_mmd=dataflow_mmd,
        dataflow_html=dataflow_html,
        combo_mmd=combo_mmd,
        combo_html=combo_html,
        reactflow_viewspec=reactflow_viewspec,
        reactflow_html=reactflow_html,
    )
