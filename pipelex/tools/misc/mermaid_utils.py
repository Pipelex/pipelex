"""Mermaid utilities for generating and rendering Mermaid diagrams.

This module provides helper functions for:
- Encoding Mermaid diagrams to shareable URLs
- Sanitizing and escaping strings for Mermaid syntax
- Rendering Mermaid code to standalone HTML pages
"""

import base64
import hashlib
import json
import zlib

from pipelex import pretty_print
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async, render_jinja2_sync

# -----------------------------------------------------------------------------
# Encoding utilities for Mermaid URLs
# -----------------------------------------------------------------------------


def encode_pako_encore_from_bytes(state_bytes: bytes) -> str:
    compressed = zlib.compress(state_bytes, level=9)
    serialized_string = base64.urlsafe_b64encode(compressed).decode("utf-8")
    return f"pako:{serialized_string}"


def encode_pako_from_string(state: str) -> str:
    state_bytes = state.encode("utf-8")
    return encode_pako_encore_from_bytes(state_bytes)


def make_mermaid_url(mermaid_code: str) -> str:
    as_dict = {
        "code": mermaid_code,
        "mermaid": {
            "theme": "default",
        },
    }
    encoded = encode_pako_from_string(json.dumps(as_dict))
    return f"https://mermaid.ink/svg/{encoded}"


def print_mermaid_url(url: str, title: str):
    pretty_print("⚠️  Warning: By clicking on the following mermaid URL, you send data to https://mermaid.live/.", border_style="red")
    pretty_print(url, title=title, border_style="yellow")


# -----------------------------------------------------------------------------
# Sanitization and escaping utilities for Mermaid syntax
# -----------------------------------------------------------------------------


def clean_str_for_mermaid_node_title(text: str) -> str:
    """Cleans a string to be safely used as a Mermaid node title by replacing quotes
    with similar Unicode characters that won't interfere with Mermaid syntax.

    Args:
        text: The string to clean

    Returns:
        The cleaned string with quotes replaced

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

    Args:
        label: The label text to escape.

    Returns:
        Escaped label safe for use in Mermaid syntax.
    """
    # Escape quotes and other special characters
    return label.replace('"', "'").replace("[", "(").replace("]", ")")


# -----------------------------------------------------------------------------
# HTML rendering for Mermaid diagrams
# -----------------------------------------------------------------------------


# HTML template for rendering Mermaid diagrams
# The mermaid_code is inserted unescaped since it's plain text for Mermaid parsing
MERMAID_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        h1 {
            color: #333;
            margin-bottom: 20px;
        }
        .mermaid-container {
            background-color: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }
        .mermaid {
            display: flex;
            justify-content: center;
        }
    </style>
</head>
<body>
    <h1>{{ title }}</h1>
    <div class="mermaid-container">
        <div class="mermaid">
{{ mermaid_code }}
        </div>
    </div>
    <script>
        mermaid.initialize({
            startOnLoad: true,
            theme: 'default',
            flowchart: {
                useMaxWidth: true,
                htmlLabels: true,
                curve: 'basis'
            }
        });
    </script>
</body>
</html>
"""


# Interactive HTML template with clickable stuff nodes that show full data
MERMAID_INTERACTIVE_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        h1 {
            color: #333;
            margin-bottom: 20px;
        }
        .mermaid-container {
            background-color: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }
        .mermaid {
            display: flex;
            justify-content: center;
        }
        .data-modal {
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: #1e1e1e;
            color: #d4d4d4;
            padding: 20px;
            border-radius: 12px;
            max-width: 80vw;
            max-height: 80vh;
            overflow: auto;
            z-index: 1000;
            display: none;
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 13px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
        }
        .data-modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid #444;
        }
        .data-modal-title {
            font-size: 16px;
            font-weight: 600;
            color: #fff;
        }
        .data-modal-close {
            cursor: pointer;
            color: #888;
            font-size: 24px;
            line-height: 1;
            padding: 4px 8px;
            border-radius: 4px;
            transition: background 0.2s;
        }
        .data-modal-close:hover {
            background: #333;
            color: #fff;
        }
        .data-modal-content {
            white-space: pre-wrap;
            word-wrap: break-word;
            line-height: 1.5;
        }
        .data-modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            z-index: 999;
            display: none;
        }
        .clickable-stuff {
            cursor: pointer !important;
        }
        .clickable-stuff:hover {
            filter: brightness(1.1);
        }
        .hint {
            color: #666;
            font-size: 14px;
            margin-top: 16px;
            text-align: center;
        }
    </style>
</head>
<body>
    <h1>{{ title }}</h1>
    <div class="mermaid-container">
        <div class="mermaid">
{{ mermaid_code }}
        </div>
    </div>
    {% if has_data %}
    <p class="hint">Click on data nodes (orange pills) to view their full content</p>
    {% endif %}
    <div class="data-modal-overlay" id="modal-overlay"></div>
    <div class="data-modal" id="data-modal">
        <div class="data-modal-header">
            <span class="data-modal-title" id="modal-title">Data Content</span>
            <span class="data-modal-close" onclick="hideModal()">&times;</span>
        </div>
        <pre class="data-modal-content" id="modal-content"></pre>
    </div>
    <script>
        // Embedded stuff data from graph
        const stuffData = {{ stuff_data_json }};

        mermaid.initialize({
            startOnLoad: true,
            theme: 'default',
            flowchart: {
                useMaxWidth: true,
                htmlLabels: true,
                curve: 'basis'
            }
        });

        // Wait for mermaid to render, then attach click handlers
        setTimeout(() => {
            // Find all stuff nodes (IDs starting with 's_')
            const svgContainer = document.querySelector('.mermaid svg');
            if (!svgContainer) return;

            // Find nodes by their flowchart IDs
            for (const stuffId of Object.keys(stuffData)) {
                // Mermaid generates IDs like 'flowchart-s_xxx-123'
                const nodes = svgContainer.querySelectorAll(`[id^="flowchart-${stuffId}"]`);
                nodes.forEach(node => {
                    node.classList.add('clickable-stuff');
                    node.addEventListener('click', (e) => {
                        e.stopPropagation();
                        showModal(stuffId, stuffData[stuffId]);
                    });
                });
            }
        }, 500);

        function showModal(stuffId, data) {
            const modal = document.getElementById('data-modal');
            const overlay = document.getElementById('modal-overlay');
            const title = document.getElementById('modal-title');
            const content = document.getElementById('modal-content');

            title.textContent = `Data: ${stuffId}`;
            content.textContent = JSON.stringify(data, null, 2);
            modal.style.display = 'block';
            overlay.style.display = 'block';
        }

        function hideModal() {
            document.getElementById('data-modal').style.display = 'none';
            document.getElementById('modal-overlay').style.display = 'none';
        }

        // Close modal when clicking overlay
        document.getElementById('modal-overlay').addEventListener('click', hideModal);

        // Close modal with Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') hideModal();
        });
    </script>
</body>
</html>
"""


def render_mermaid_html(
    mermaid_code: str,
    *,
    title: str = "Pipelex Graph",
) -> str:
    """Render Mermaid code into a standalone HTML page (sync version).

    Use this when NOT inside an async event loop. For async contexts,
    use render_mermaid_html_async instead.

    Args:
        mermaid_code: The Mermaid flowchart code to embed.
        title: The page title (appears in browser tab and as h1).

    Returns:
        Complete HTML page as a string.
    """
    return render_jinja2_sync(
        template_source=MERMAID_HTML_TEMPLATE,
        template_category=TemplateCategory.HTML,
        temlating_context={
            "title": title,
            "mermaid_code": mermaid_code,
        },
    )


async def render_mermaid_html_async(
    mermaid_code: str,
    *,
    title: str = "Pipelex Graph",
) -> str:
    """Render Mermaid code into a standalone HTML page (async version).

    Use this when inside an async event loop.

    Args:
        mermaid_code: The Mermaid flowchart code to embed.
        title: The page title (appears in browser tab and as h1).

    Returns:
        Complete HTML page as a string.
    """
    return await render_jinja2_async(
        template_source=MERMAID_HTML_TEMPLATE,
        template_category=TemplateCategory.HTML,
        temlating_context={
            "title": title,
            "mermaid_code": mermaid_code,
        },
    )


async def render_mermaid_html_with_data_async(
    mermaid_code: str,
    stuff_data: dict[str, str | dict[str, object] | list[str] | list[dict[str, object]] | None],
    *,
    title: str = "Pipelex Graph",
) -> str:
    """Render Mermaid code with clickable stuff nodes into a standalone HTML page.

    This renders an interactive version where clicking on stuff nodes (data items)
    displays their full serialized content in a modal dialog.

    Args:
        mermaid_code: The Mermaid flowchart code to embed.
        stuff_data: Mapping from stuff mermaid IDs to their full data content.
        title: The page title (appears in browser tab and as h1).

    Returns:
        Complete HTML page as a string with interactive data display.
    """
    return await render_jinja2_async(
        template_source=MERMAID_INTERACTIVE_HTML_TEMPLATE,
        template_category=TemplateCategory.HTML,
        temlating_context={
            "title": title,
            "mermaid_code": mermaid_code,
            "stuff_data_json": json.dumps(stuff_data),
            "has_data": bool(stuff_data),
        },
    )
