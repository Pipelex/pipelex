"""Mermaid HTML rendering for graph visualization.

This module provides functions to render Mermaid code into standalone HTML pages
with theme support and interactive features for viewing stuff (data) content.
"""

import json
from typing import Any

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async, render_jinja2_sync
from pipelex.tools.jinja2.jinja2_template_registry import TemplateRegistry

# Template registry keys
_BASIC_TEMPLATE_KEY = "mermaid/basic.html.jinja2"
_INTERACTIVE_TEMPLATE_KEY = "mermaid/interactive.html.jinja2"


def render_mermaid_html(
    mermaid_code: str,
    *,
    title: str = "Pipelex Graph",
    theme: str = "dark",
) -> str:
    """Render Mermaid code into a standalone HTML page (sync version).

    Use this when NOT inside an async event loop. For async contexts,
    use render_mermaid_html_async instead.

    Args:
        mermaid_code: The Mermaid flowchart code to embed.
        title: The page title (appears in browser tab and as h1).
        theme: The Mermaid theme to use (dark, default, base, forest, neutral).

    Returns:
        Complete HTML page as a string.
    """
    template_source = TemplateRegistry.get(_BASIC_TEMPLATE_KEY)
    return render_jinja2_sync(
        template_source=template_source,
        template_category=TemplateCategory.HTML,
        templating_context={
            "title": title,
            "mermaid_code": mermaid_code,
            "theme": theme,
        },
        use_registry=True,  # Use registry for templates with includes
    )


async def render_mermaid_html_async(
    mermaid_code: str,
    *,
    title: str = "Pipelex Graph",
    theme: str = "dark",
) -> str:
    """Render Mermaid code into a standalone HTML page (async version).

    Use this when inside an async event loop.

    Args:
        mermaid_code: The Mermaid flowchart code to embed.
        title: The page title (appears in browser tab and as h1).
        theme: The Mermaid theme to use (dark, default, base, forest, neutral).

    Returns:
        Complete HTML page as a string.
    """
    template_source = TemplateRegistry.get(_BASIC_TEMPLATE_KEY)
    return await render_jinja2_async(
        template_source=template_source,
        template_category=TemplateCategory.HTML,
        templating_context={
            "title": title,
            "mermaid_code": mermaid_code,
            "theme": theme,
        },
        use_registry=True,  # Use registry for templates with includes
    )


async def render_mermaid_html_with_data_async(
    mermaid_code: str,
    stuff_data: dict[str, str | dict[str, object] | list[str] | list[dict[str, object]] | None] | None = None,
    stuff_data_text: dict[str, str] | None = None,
    stuff_data_html: dict[str, str] | None = None,
    stuff_metadata: dict[str, dict[str, str]] | None = None,
    stuff_content_type: dict[str, str] | None = None,
    *,
    title: str = "Pipelex Graph",
    theme: str = "dark",
) -> str:
    """Render Mermaid code with clickable stuff nodes into a standalone HTML page.

    This renders an interactive version where clicking on stuff nodes (data items)
    displays their full serialized content in a modal dialog. Supports multiple
    display formats (JSON, Text, HTML) with runtime toggle.

    Args:
        mermaid_code: The Mermaid flowchart code to embed.
        stuff_data: Mapping from stuff mermaid IDs to their full data content (JSON format).
        stuff_data_text: Mapping from stuff mermaid IDs to their ASCII text representation.
        stuff_data_html: Mapping from stuff mermaid IDs to their HTML representation.
        stuff_metadata: Mapping from stuff mermaid IDs to their display metadata (name, concept).
        stuff_content_type: Mapping from stuff mermaid IDs to their content_type (e.g., 'application/pdf').
        title: The page title (appears in browser tab and as h1).
        theme: The Mermaid theme to use (dark, default, base, forest, neutral).

    Returns:
        Complete HTML page as a string with interactive data display.
    """
    template_source = TemplateRegistry.get(_INTERACTIVE_TEMPLATE_KEY)
    has_data = bool(stuff_data or stuff_data_text or stuff_data_html)

    # Pre-serialize the data to JSON for embedding in the template
    context: dict[str, Any] = {
        "title": title,
        "mermaid_code": mermaid_code,
        "stuff_data_json": json.dumps(stuff_data or {}),
        "stuff_data_text_json": json.dumps(stuff_data_text or {}),
        "stuff_data_html_json": json.dumps(stuff_data_html or {}),
        "stuff_metadata_json": json.dumps(stuff_metadata or {}),
        "stuff_content_type_json": json.dumps(stuff_content_type or {}),
        "has_data": has_data,
        "theme": theme,
    }

    return await render_jinja2_async(
        template_source=template_source,
        template_category=TemplateCategory.HTML,
        templating_context=context,
        use_registry=True,  # Use registry for templates with includes
    )
