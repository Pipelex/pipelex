"""HTML renderer for Mermaid flowcharts.

This module renders Mermaid code into a standalone HTML page that can be
viewed in a browser.
"""

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async, render_jinja2_sync

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
