"""Graph output factory for generating graph content.

This module provides factory functions for generating graph outputs including
JSON, Mermaid, ReactFlow, and HTML content for orchestration, data flow, and combo views.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from pipelex.graph.graph_analysis import GraphAnalysis
from pipelex.graph.graph_config import DataInclusion, GraphConfig, GraphsInclusion
from pipelex.graph.graphspec_io import graphspec_to_json
from pipelex.graph.mermaid import (
    graphspec_to_combo_mermaid,
    graphspec_to_combo_mermaid_with_data,
    graphspec_to_dataflow_mermaid,
    graphspec_to_dataflow_mermaid_with_data,
    graphspec_to_orchestration_mermaid,
)
from pipelex.graph.reactflow_html import generate_reactflow_html_async
from pipelex.graph.viewspec_transformer import graphspec_to_viewspec
from pipelex.tools.misc.chart_utils import FlowchartDirection
from pipelex.tools.misc.mermaid_utils import render_mermaid_html_async, render_mermaid_html_with_data_async

if TYPE_CHECKING:
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
    include_full_data = graph_config.data_inclusion.get(DataInclusion.STUFF_JSON_CONTENT, False)

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
    if inclusion.get(GraphsInclusion.GRAPHSPEC_JSON, True):
        graphspec_json = graphspec_to_json(graph_spec)

    # Generate orchestration view
    if inclusion.get(GraphsInclusion.ORCHESTRATION_MMD, True):
        orchestration_mmd = graphspec_to_orchestration_mermaid(graph_spec, direction=direction)

    if inclusion.get(GraphsInclusion.ORCHESTRATION_HTML, True):
        # Need the mermaid code to generate HTML
        mmd_for_html = orchestration_mmd or graphspec_to_orchestration_mermaid(graph_spec, direction=direction)
        orchestration_html = await render_mermaid_html_async(mmd_for_html, title=f"Orchestration: {pipe_code}")

    # Generate data flow view
    if inclusion.get(GraphsInclusion.DATAFLOW_MMD, True) or inclusion.get(GraphsInclusion.DATAFLOW_HTML, True):
        if include_full_data:
            dataflow_with_data = graphspec_to_dataflow_mermaid_with_data(graph_spec, direction=direction)
            if inclusion.get(GraphsInclusion.DATAFLOW_MMD, True):
                dataflow_mmd = dataflow_with_data.mermaid_code
            if inclusion.get(GraphsInclusion.DATAFLOW_HTML, True):
                dataflow_html = await render_mermaid_html_with_data_async(
                    dataflow_with_data.mermaid_code,
                    stuff_data=dataflow_with_data.stuff_data,
                    title=f"Data Flow: {pipe_code}",
                )
        else:
            mmd_code = graphspec_to_dataflow_mermaid(graph_spec, direction=direction)
            if inclusion.get(GraphsInclusion.DATAFLOW_MMD, True):
                dataflow_mmd = mmd_code
            if inclusion.get(GraphsInclusion.DATAFLOW_HTML, True):
                dataflow_html = await render_mermaid_html_async(mmd_code, title=f"Data Flow: {pipe_code}")

    # Generate combo view
    if inclusion.get(GraphsInclusion.COMBO_MMD, True) or inclusion.get(GraphsInclusion.COMBO_HTML, True):
        if include_full_data:
            combo_with_data = graphspec_to_combo_mermaid_with_data(graph_spec, direction=direction)
            if inclusion.get(GraphsInclusion.COMBO_MMD, True):
                combo_mmd = combo_with_data.mermaid_code
            if inclusion.get(GraphsInclusion.COMBO_HTML, True):
                combo_html = await render_mermaid_html_with_data_async(
                    combo_with_data.mermaid_code,
                    stuff_data=combo_with_data.stuff_data,
                    title=f"Combo: {pipe_code}",
                )
        else:
            mmd_code = graphspec_to_combo_mermaid(graph_spec, direction=direction)
            if inclusion.get(GraphsInclusion.COMBO_MMD, True):
                combo_mmd = mmd_code
            if inclusion.get(GraphsInclusion.COMBO_HTML, True):
                combo_html = await render_mermaid_html_async(mmd_code, title=f"Combo: {pipe_code}")

    # Generate ReactFlow outputs
    if inclusion.get(GraphsInclusion.REACTFLOW_VIEWSPEC, True) or inclusion.get(GraphsInclusion.REACTFLOW_HTML, True):
        analysis = GraphAnalysis.from_graphspec(graph_spec)
        viewspec = graphspec_to_viewspec(graph_spec, analysis)

        if inclusion.get(GraphsInclusion.REACTFLOW_VIEWSPEC, True):
            reactflow_viewspec = viewspec.model_dump_json(indent=2)

        if inclusion.get(GraphsInclusion.REACTFLOW_HTML, True):
            reactflow_html = await generate_reactflow_html_async(
                viewspec,
                graphspec=graph_spec,
                use_cdn=graph_config.reactflow_config.is_use_cdn,
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
