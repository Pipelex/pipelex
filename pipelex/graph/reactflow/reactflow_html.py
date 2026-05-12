"""ReactFlow HTML generator for GraphSpec rendering.

Generates standalone HTML files using the mthds-ui GraphViewer component.
The HTML template uses Jinja2 for data injection, consistent with mermaid rendering.
JS and CSS bundles are loaded from vendored assets.
"""

import json

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.graph.graphspec import GraphSpec
from pipelex.graph.reactflow.reactflow_config import ReactFlowRenderingConfig
from pipelex.graph.reactflow.standalone_assets import get_standalone_css, get_standalone_js
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async, render_jinja2_sync
from pipelex.tools.jinja2.jinja2_template_registry import TemplateRegistry

_REACTFLOW_TEMPLATE_KEY = "reactflow/main.html.jinja2"


def _build_viewer_config(config: ReactFlowRenderingConfig) -> dict[str, object]:
    """Build the viewer config dict from the ReactFlow rendering config."""
    return {
        "direction": config.layout_direction.reactflow_code,
        "showControllers": config.show_batch_controller,
        "nodesep": config.nodesep,
        "ranksep": config.ranksep,
        "edgeType": config.edge_type,
        "initialZoom": config.initial_zoom,
        "panToTop": config.pan_to_top,
        "palette": config.style.palette,
    }


def generate_reactflow_html(
    graphspec: GraphSpec,
    config: ReactFlowRenderingConfig,
    *,
    title: str | None = None,
) -> str:
    """Generate single-file HTML with embedded GraphSpec and mthds-ui GraphViewer.

    Args:
        graphspec: The GraphSpec to embed and render.
        config: ReactFlow rendering configuration.
        title: Optional page title, overrides config.default_title.

    Returns:
        Complete HTML page as a string with embedded GraphViewer.
    """
    template_source = TemplateRegistry.get(_REACTFLOW_TEMPLATE_KEY)

    graphspec_json = json.dumps(graphspec.model_dump(mode="json", by_alias=True), indent=2)
    config_json = json.dumps(_build_viewer_config(config))

    return render_jinja2_sync(
        template_source=template_source,
        template_category=TemplateCategory.HTML,
        templating_context={
            "title": title or config.default_title,
            "graphspec_json": graphspec_json,
            "config_json": config_json,
            "theme": config.style.theme,
            "viewer_js": get_standalone_js(),
            "viewer_css": get_standalone_css(),
        },
    )


async def generate_reactflow_html_async(
    graphspec: GraphSpec,
    config: ReactFlowRenderingConfig,
    *,
    title: str | None = None,
) -> str:
    """Generate single-file HTML with embedded GraphSpec and mthds-ui GraphViewer (async version).

    Args:
        graphspec: The GraphSpec to embed and render.
        config: ReactFlow rendering configuration.
        title: Optional page title, overrides config.default_title.

    Returns:
        Complete HTML page as a string with embedded GraphViewer.
    """
    template_source = TemplateRegistry.get(_REACTFLOW_TEMPLATE_KEY)

    graphspec_json = json.dumps(graphspec.model_dump(mode="json", by_alias=True), indent=2)
    config_json = json.dumps(_build_viewer_config(config))

    return await render_jinja2_async(
        template_source=template_source,
        template_category=TemplateCategory.HTML,
        templating_context={
            "title": title or config.default_title,
            "graphspec_json": graphspec_json,
            "config_json": config_json,
            "theme": config.style.theme,
            "viewer_js": get_standalone_js(),
            "viewer_css": get_standalone_css(),
        },
    )
