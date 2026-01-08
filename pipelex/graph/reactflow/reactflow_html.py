"""ReactFlow HTML generator for ViewSpec rendering.

This module provides functions to generate standalone HTML files with embedded
ReactFlow viewers that can render ViewSpec graphs interactively.
"""

import json

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.graph.graphspec import GraphSpec
from pipelex.graph.reactflow.reactflow_config import ReactFlowRenderingConfig
from pipelex.graph.reactflow.viewspec import ViewSpec
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async, render_jinja2_sync
from pipelex.tools.jinja2.jinja2_template_registry import TemplateRegistry
from pipelex.urls import URLs

# Template key in the registry
_REACTFLOW_TEMPLATE_KEY = "reactflow/main.html.jinja2"


def generate_reactflow_html(
    viewspec: ViewSpec,
    config: ReactFlowRenderingConfig,
    *,
    graphspec: GraphSpec | None = None,
    stuff_data_text: dict[str, str] | None = None,
    stuff_data_html: dict[str, str] | None = None,
    title: str | None = None,
) -> str:
    """Generate single-file HTML with embedded ViewSpec and ReactFlow viewer.

    Args:
        viewspec: The ViewSpec to embed and render.
        config: ReactFlow rendering configuration.
        graphspec: Optional GraphSpec to embed (for inspector details).
        stuff_data_text: Optional mapping from stuff IDs to their ASCII text representation.
        stuff_data_html: Optional mapping from stuff IDs to their HTML representation.
        title: Optional page title, overrides config.default_title.

    Returns:
        Complete HTML page as a string with embedded ReactFlow viewer.
    """
    # Get template from pre-loaded registry (sandbox-safe, no I/O at render time)
    template_source = TemplateRegistry.get(_REACTFLOW_TEMPLATE_KEY)

    # Serialize ViewSpec to JSON
    viewspec_json = json.dumps(viewspec.model_dump(mode="json"), indent=2)

    # Serialize GraphSpec to JSON if provided
    graphspec_json: str | None = None
    if graphspec:
        graphspec_json = json.dumps(graphspec.model_dump(mode="json"), indent=2)

    # Render template (use_registry=True to support {% include %} directives)
    return render_jinja2_sync(
        template_source=template_source,
        template_category=TemplateCategory.HTML,
        templating_context={
            "title": title or config.default_title,
            "logo_dark": URLs.logo_white_on_transparent,
            "logo_light": URLs.logo_black_on_transparent,
            "viewspec_json": viewspec_json,
            "graphspec_json": graphspec_json,
            "stuff_data_text_json": json.dumps(stuff_data_text or {}),
            "stuff_data_html_json": json.dumps(stuff_data_html or {}),
            "use_cdn": config.is_use_cdn,
            "nodesep": config.nodesep,
            "ranksep": config.ranksep,
            "edge_type": config.edge_type,
            "initial_zoom": config.initial_zoom,
            "pan_to_top": config.pan_to_top,
            "initial_theme": config.style.theme,
        },
        use_registry=True,
    )


async def generate_reactflow_html_async(
    viewspec: ViewSpec,
    config: ReactFlowRenderingConfig,
    *,
    graphspec: GraphSpec | None = None,
    stuff_data_text: dict[str, str] | None = None,
    stuff_data_html: dict[str, str] | None = None,
    title: str | None = None,
) -> str:
    """Generate single-file HTML with embedded ViewSpec and ReactFlow viewer (async version).

    Use this when inside an async event loop.

    Args:
        viewspec: The ViewSpec to embed and render.
        config: ReactFlow rendering configuration.
        graphspec: Optional GraphSpec to embed (for inspector details).
        stuff_data_text: Optional mapping from stuff IDs to their ASCII text representation.
        stuff_data_html: Optional mapping from stuff IDs to their HTML representation.
        title: Optional page title, overrides config.default_title.

    Returns:
        Complete HTML page as a string with embedded ReactFlow viewer.
    """
    # Get template from pre-loaded registry (sandbox-safe, no I/O at render time)
    template_source = TemplateRegistry.get(_REACTFLOW_TEMPLATE_KEY)

    # Serialize ViewSpec to JSON
    viewspec_json = json.dumps(viewspec.model_dump(mode="json"), indent=2)

    # Serialize GraphSpec to JSON if provided
    graphspec_json: str | None = None
    if graphspec:
        graphspec_json = json.dumps(graphspec.model_dump(mode="json"), indent=2)

    # Render template (use_registry=True to support {% include %} directives)
    return await render_jinja2_async(
        template_source=template_source,
        template_category=TemplateCategory.HTML,
        templating_context={
            "title": title or config.default_title,
            "logo_dark": URLs.logo_white_on_transparent,
            "logo_light": URLs.logo_black_on_transparent,
            "viewspec_json": viewspec_json,
            "graphspec_json": graphspec_json,
            "stuff_data_text_json": json.dumps(stuff_data_text or {}),
            "stuff_data_html_json": json.dumps(stuff_data_html or {}),
            "use_cdn": config.is_use_cdn,
            "nodesep": config.nodesep,
            "ranksep": config.ranksep,
            "edge_type": config.edge_type,
            "initial_zoom": config.initial_zoom,
            "pan_to_top": config.pan_to_top,
            "initial_theme": config.style.theme,
        },
        use_registry=True,
    )
