"""ReactFlow HTML generator for GraphSpec rendering.

Generates standalone HTML files using the mthds-ui GraphViewer component.
The pre-built HTML template (with JS+CSS inlined) is loaded from assets/
and injected with GraphSpec data and configuration.
"""

import json
import re
from html import escape as html_escape

from pipelex.graph.graphspec import GraphSpec
from pipelex.graph.reactflow.reactflow_config import ReactFlowRenderingConfig
from pipelex.graph.reactflow.standalone_assets import get_standalone_template
from pipelex.urls import URLs


def _escape_script_json(json_str: str) -> str:
    """Escape </script> in JSON to prevent premature script tag closure."""
    return re.sub(r"</script>", r"<\\/script>", json_str, flags=re.IGNORECASE)


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
    }


def generate_reactflow_html(
    graphspec: GraphSpec,
    config: ReactFlowRenderingConfig,
    *,
    stuff_data_text: dict[str, str] | None = None,  # noqa: ARG001 — kept for backward compat
    stuff_data_html: dict[str, str] | None = None,  # noqa: ARG001 — kept for backward compat
    title: str | None = None,
) -> str:
    """Generate single-file HTML with embedded GraphSpec and mthds-ui GraphViewer.

    Args:
        graphspec: The GraphSpec to embed and render.
        config: ReactFlow rendering configuration.
        stuff_data_text: Unused (kept for backward compatibility). Data is in GraphSpec IOSpec fields.
        stuff_data_html: Unused (kept for backward compatibility). Data is in GraphSpec IOSpec fields.
        title: Optional page title, overrides config.default_title.

    Returns:
        Complete HTML page as a string with embedded GraphViewer.
    """
    template = get_standalone_template()

    graphspec_json = json.dumps(graphspec.model_dump(mode="json", by_alias=True), indent=2)
    config_json = json.dumps(_build_viewer_config(config))
    page_title = title or config.default_title

    return (
        template.replace("<!--PIPELEX_TITLE-->", html_escape(page_title))
        .replace("<!--PIPELEX_GRAPHSPEC-->", _escape_script_json(graphspec_json))
        .replace("<!--PIPELEX_CONFIG-->", config_json)
        .replace("<!--PIPELEX_LOGO_DARK-->", URLs.logo_white_on_transparent)
        .replace("<!--PIPELEX_LOGO_LIGHT-->", URLs.logo_black_on_transparent)
        .replace("<!--PIPELEX_THEME-->", config.style.theme)
    )


async def generate_reactflow_html_async(  # noqa: RUF029 — async signature kept for call-site compat
    graphspec: GraphSpec,
    config: ReactFlowRenderingConfig,
    *,
    stuff_data_text: dict[str, str] | None = None,
    stuff_data_html: dict[str, str] | None = None,
    title: str | None = None,
) -> str:
    """Generate single-file HTML with embedded GraphSpec and mthds-ui GraphViewer (async version).

    Delegates to the sync version since no I/O is performed (template is cached).

    Args:
        graphspec: The GraphSpec to embed and render.
        config: ReactFlow rendering configuration.
        stuff_data_text: Unused (kept for backward compatibility).
        stuff_data_html: Unused (kept for backward compatibility).
        title: Optional page title, overrides config.default_title.

    Returns:
        Complete HTML page as a string with embedded GraphViewer.
    """
    return generate_reactflow_html(
        graphspec=graphspec,
        config=config,
        stuff_data_text=stuff_data_text,
        stuff_data_html=stuff_data_html,
        title=title,
    )
