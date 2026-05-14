"""ReactFlow HTML generator for GraphSpec rendering.

Generates HTML files using the mthds-ui GraphViewer component, loaded from
jsDelivr with Subresource Integrity. The template uses Jinja2 for data
injection, consistent with mermaid rendering.
"""

import json

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.graph.graphspec import GraphSpec
from pipelex.graph.reactflow.reactflow_config import ReactFlowRenderingConfig
from pipelex.graph.reactflow.standalone_assets import ELKJS, MTHDS_UI_CSS, MTHDS_UI_JS
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


def _build_templating_context(
    graphspec: GraphSpec,
    config: ReactFlowRenderingConfig,
    title: str | None,
) -> dict[str, object]:
    return {
        "title": title or config.default_title,
        "graphspec_json": json.dumps(graphspec.model_dump(mode="json", by_alias=True), indent=2),
        "config_json": json.dumps(_build_viewer_config(config)),
        "theme": config.style.theme,
        "mthds_ui_js": MTHDS_UI_JS,
        "mthds_ui_css": MTHDS_UI_CSS,
        "elkjs": ELKJS,
    }


def generate_reactflow_html(
    graphspec: GraphSpec,
    config: ReactFlowRenderingConfig,
    *,
    title: str | None = None,
) -> str:
    """Generate HTML with embedded GraphSpec; viewer assets load from jsDelivr (SRI-pinned).

    Args:
        graphspec: The GraphSpec to embed and render.
        config: ReactFlow rendering configuration.
        title: Optional page title, overrides config.default_title.

    Returns:
        Complete HTML page as a string.
    """
    template_source = TemplateRegistry.get(_REACTFLOW_TEMPLATE_KEY)
    return render_jinja2_sync(
        template_source=template_source,
        template_category=TemplateCategory.HTML,
        templating_context=_build_templating_context(graphspec, config, title),
    )


async def generate_reactflow_html_async(
    graphspec: GraphSpec,
    config: ReactFlowRenderingConfig,
    *,
    title: str | None = None,
) -> str:
    """Async variant of `generate_reactflow_html`."""
    template_source = TemplateRegistry.get(_REACTFLOW_TEMPLATE_KEY)
    return await render_jinja2_async(
        template_source=template_source,
        template_category=TemplateCategory.HTML,
        templating_context=_build_templating_context(graphspec, config, title),
    )
