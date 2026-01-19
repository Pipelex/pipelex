"""Standalone HTML viewer rendering for Stuff content.

This module provides functions to render a Stuff object as a standalone HTML viewer page
with format tabs (HTML/JSON/Pretty) and action buttons (copy, download, open external).
"""

import json
from typing import Any

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.core.stuffs.stuff import Stuff
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async
from pipelex.tools.jinja2.jinja2_template_registry import TemplateRegistry
from pipelex.tools.misc.pretty import PRETTY_WIDTH_FOR_EXPORT

# Template registry key
_STUFF_VIEWER_TEMPLATE_KEY = "stuff/stuff_viewer.html.jinja2"


async def render_stuff_viewer(
    stuff: Stuff,
    *,
    title: str | None = None,
    subtitle: str | None = None,
) -> str:
    """Render a Stuff object as a standalone HTML viewer page.

    Creates an HTML page with format tabs (HTML/JSON/Pretty) and action buttons
    (copy, download, open external). Uses the shared templates for consistent
    styling with graph visualizations.

    Args:
        stuff: The Stuff object to render.
        title: Page title. Defaults to the stuff's title.
        subtitle: Optional subtitle (e.g., concept info).

    Returns:
        Complete HTML page as a string.
    """
    # Prepare title
    display_title = title or stuff.title
    display_subtitle = subtitle or f"Concept: {stuff.concept.code}"

    # Get content data in various formats
    stuff_data = stuff.content.smart_dump()
    stuff_data_text = stuff.content.rendered_pretty_text(width=PRETTY_WIDTH_FOR_EXPORT)
    stuff_data_html = await stuff.content.rendered_html_async()
    content_type = stuff.content.content_type

    # Determine HTML tab label based on content type
    html_tab_label = _get_html_tab_label(content_type)

    # Get template and render
    template_source = TemplateRegistry.get(_STUFF_VIEWER_TEMPLATE_KEY)
    return await render_jinja2_async(
        template_source=template_source,
        template_category=TemplateCategory.HTML,
        templating_context={
            "title": display_title,
            "subtitle": display_subtitle,
            "html_tab_label": html_tab_label,
            "stuff_data_json": json.dumps(stuff_data),
            "stuff_data_text_json": json.dumps(stuff_data_text),
            "stuff_data_html_json": json.dumps(stuff_data_html),
            "content_type_json": json.dumps(content_type),
        },
        use_registry=True,
    )


async def render_stuff_content_viewer(
    stuff_data: str | dict[str, Any] | list[str] | list[dict[str, Any]],
    stuff_data_text: str,
    stuff_data_html: str,
    content_type: str | None = None,
    *,
    title: str = "Stuff Content",
    subtitle: str | None = None,
) -> str:
    """Render pre-computed stuff content as a standalone HTML viewer page.

    Use this when you already have the various content representations
    (e.g., from IOSpec objects or pre-computed data).

    Args:
        stuff_data: The JSON-serializable content data.
        stuff_data_text: Plain text representation (pretty print).
        stuff_data_html: HTML representation.
        content_type: MIME type (e.g., 'application/pdf', 'image/png').
        title: Page title.
        subtitle: Optional subtitle.

    Returns:
        Complete HTML page as a string.
    """
    # Determine HTML tab label based on content type
    html_tab_label = _get_html_tab_label(content_type)

    # Get template and render
    template_source = TemplateRegistry.get(_STUFF_VIEWER_TEMPLATE_KEY)
    return await render_jinja2_async(
        template_source=template_source,
        template_category=TemplateCategory.HTML,
        templating_context={
            "title": title,
            "subtitle": subtitle,
            "html_tab_label": html_tab_label,
            "stuff_data_json": json.dumps(stuff_data),
            "stuff_data_text_json": json.dumps(stuff_data_text),
            "stuff_data_html_json": json.dumps(stuff_data_html),
            "content_type_json": json.dumps(content_type),
        },
        use_registry=True,
    )


def _get_html_tab_label(content_type: str | None) -> str:
    """Get the appropriate tab label based on content type."""
    if content_type == "application/pdf":
        return "PDF"
    if content_type and content_type.startswith("image/"):
        return "Image"
    return "HTML"
