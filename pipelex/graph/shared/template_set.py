"""Shared template set definition.

This module defines the shared templates used by both mermaidflow and reactflow
for displaying stuff (data) content. These templates are registered at boot time
for sandbox-safe rendering.
"""

# Template set name
SHARED_TEMPLATE_SET_NAME: str = "shared"

# Package path where templates are located
SHARED_TEMPLATES_PACKAGE: str = "pipelex.graph.shared.templates"

# List of (filename, registry_key) tuples
SHARED_TEMPLATES: list[tuple[str, str]] = [
    ("_stuff_utils.js.jinja2", "shared/_stuff_utils.js.jinja2"),
    ("_stuff_format_tabs.css.jinja2", "shared/_stuff_format_tabs.css.jinja2"),
    ("_stuff_content_styles.css.jinja2", "shared/_stuff_content_styles.css.jinja2"),
    ("_stuff_icons.html.jinja2", "shared/_stuff_icons.html.jinja2"),
]

# Tuple of (name, package, templates) for convenient single import
SHARED_TEMPLATE_SET: tuple[str, str, list[tuple[str, str]]] = (
    SHARED_TEMPLATE_SET_NAME,
    SHARED_TEMPLATES_PACKAGE,
    SHARED_TEMPLATES,
)
