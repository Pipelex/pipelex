"""Generic Mermaid utilities for encoding and escaping.

This module provides helper functions for:
- Encoding Mermaid diagrams to shareable URLs
- Sanitizing and escaping strings for Mermaid syntax

For HTML rendering of Mermaid diagrams with themes and interactivity,
see pipelex.graph.mermaid_html (Pipelex-specific) or use render_mermaid_html
from this module for generic rendering.
"""

import base64
import hashlib
import json
import zlib

from pipelex import pretty_print
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async, render_jinja2_sync
from pipelex.tools.jinja2.jinja2_template_loader import load_template

# Template package and name for generic Mermaid HTML
_TEMPLATE_PACKAGE = "pipelex.tools.mermaid.templates"
_GENERIC_TEMPLATE = "mermaid_generic.html.jinja2"


# -----------------------------------------------------------------------------
# Encoding utilities for Mermaid URLs
# -----------------------------------------------------------------------------


def encode_pako_from_bytes(state_bytes: bytes) -> str:
    """Encode bytes using pako compression for Mermaid URLs."""
    compressed = zlib.compress(state_bytes, level=9)
    serialized_string = base64.urlsafe_b64encode(compressed).decode("utf-8")
    return f"pako:{serialized_string}"


def encode_pako_from_string(state: str) -> str:
    """Encode a string using pako compression for Mermaid URLs."""
    state_bytes = state.encode("utf-8")
    return encode_pako_from_bytes(state_bytes)


def make_mermaid_url(mermaid_code: str) -> str:
    """Create a shareable mermaid.ink URL for the given code.

    Args:
        mermaid_code: The Mermaid diagram code.

    Returns:
        A URL that can be opened in a browser to view the diagram.
    """
    as_dict = {
        "code": mermaid_code,
        "mermaid": {
            "theme": "default",
        },
    }
    encoded = encode_pako_from_string(json.dumps(as_dict))
    return f"https://mermaid.ink/svg/{encoded}"


def print_mermaid_url(url: str, title: str) -> None:
    """Print a Mermaid URL with a privacy warning.

    Args:
        url: The mermaid.ink URL to print.
        title: A title for the output.
    """
    pretty_print("⚠️  Warning: By clicking on the following mermaid URL, you send data to https://mermaid.live/.", border_style="red")
    pretty_print(url, title=title, border_style="yellow")


# -----------------------------------------------------------------------------
# Sanitization and escaping utilities for Mermaid syntax
# -----------------------------------------------------------------------------


def clean_str_for_mermaid_node_title(text: str) -> str:
    """Clean a string for use as a Mermaid node title.

    Replaces quotes with similar Unicode characters that won't interfere
    with Mermaid syntax.

    Args:
        text: The string to clean.

    Returns:
        The cleaned string with quotes replaced.
    """
    # Replace single and double quotes with similar Unicode characters
    text = text.replace('"', "″")  # Replace with prime symbol
    return text.replace("'", "′")  # Replace with curly quote


def sanitize_mermaid_id(node_id: str) -> str:
    """Convert a node ID to a valid Mermaid identifier.

    Mermaid IDs cannot contain special characters like ':', '-', '.'.
    We use a hash-based approach to ensure uniqueness and validity.

    Args:
        node_id: The original node ID (may contain special characters).

    Returns:
        A sanitized Mermaid-safe identifier like 'n_abc1234567'.
    """
    # Using sha256 for hashing (only for ID generation, not security)
    hash_digest = hashlib.sha256(node_id.encode()).hexdigest()[:10]
    return f"n_{hash_digest}"


def escape_mermaid_label(label: str) -> str:
    """Escape special characters in Mermaid labels.

    Handles characters that could break Mermaid syntax or inject directives.

    Args:
        label: The label text to escape.

    Returns:
        Escaped label safe for use in Mermaid syntax.
    """
    result = label
    result = result.replace("\\", "\\\\")  # Escape backslashes first
    result = result.replace('"', "'")
    result = result.replace("[", "(")
    result = result.replace("]", ")")
    result = result.replace("{", "(")
    result = result.replace("}", ")")
    result = result.replace("<", "&lt;")
    result = result.replace(">", "&gt;")
    return result.replace("|", "/")  # Pipe can break node syntax


# -----------------------------------------------------------------------------
# Generic HTML rendering for any Mermaid diagram
# -----------------------------------------------------------------------------


def render_mermaid_html_generic(
    mermaid_code: str,
    *,
    title: str = "Mermaid Diagram",
    theme: str = "default",
) -> str:
    """Render any Mermaid code into a standalone HTML page (sync version).

    This is a generic renderer without any application-specific styling.
    Use this when NOT inside an async event loop.

    Args:
        mermaid_code: The Mermaid diagram code to embed.
        title: The page title (appears in browser tab and as h1).
        theme: The Mermaid theme to use (default, base, dark, forest, neutral).

    Returns:
        Complete HTML page as a string.
    """
    template_source = load_template(package=_TEMPLATE_PACKAGE, template_name=_GENERIC_TEMPLATE)
    return render_jinja2_sync(
        template_source=template_source,
        template_category=TemplateCategory.HTML,
        templating_context={
            "title": title,
            "mermaid_code": mermaid_code,
            "theme": theme,
        },
    )


async def render_mermaid_html_generic_async(
    mermaid_code: str,
    *,
    title: str = "Mermaid Diagram",
    theme: str = "default",
) -> str:
    """Render any Mermaid code into a standalone HTML page (async version).

    This is a generic renderer without any application-specific styling.
    Use this when inside an async event loop.

    Args:
        mermaid_code: The Mermaid diagram code to embed.
        title: The page title (appears in browser tab and as h1).
        theme: The Mermaid theme to use (default, base, dark, forest, neutral).

    Returns:
        Complete HTML page as a string.
    """
    template_source = load_template(package=_TEMPLATE_PACKAGE, template_name=_GENERIC_TEMPLATE)
    return await render_jinja2_async(
        template_source=template_source,
        template_category=TemplateCategory.HTML,
        templating_context={
            "title": title,
            "mermaid_code": mermaid_code,
            "theme": theme,
        },
    )
