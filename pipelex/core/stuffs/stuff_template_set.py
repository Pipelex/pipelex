"""Stuff template set definition.

This module defines the stuff presentation templates used for displaying
stuff (data) content in HTML viewers. These templates are used by:
- Standalone stuff HTML viewer (stuff_viewer.py)
- Graph visualizations (mermaidflow, reactflow)
"""

# Template set name
STUFF_TEMPLATE_SET_NAME: str = "stuff"

# Package path where templates are located
STUFF_TEMPLATES_PACKAGE: str = "pipelex.core.stuffs.templates"

# List of (filename, registry_key) tuples
STUFF_TEMPLATES: list[tuple[str, str]] = [
    ("_stuff_utils.js.jinja2", "stuff/_stuff_utils.js.jinja2"),
    ("_stuff_format_tabs.css.jinja2", "stuff/_stuff_format_tabs.css.jinja2"),
    ("_stuff_content_styles.css.jinja2", "stuff/_stuff_content_styles.css.jinja2"),
    ("_stuff_icons.html.jinja2", "stuff/_stuff_icons.html.jinja2"),
    ("stuff_viewer.html.jinja2", "stuff/stuff_viewer.html.jinja2"),
]

# Tuple of (name, package, templates) for convenient single import
STUFF_TEMPLATE_SET: tuple[str, str, list[tuple[str, str]]] = (
    STUFF_TEMPLATE_SET_NAME,
    STUFF_TEMPLATES_PACKAGE,
    STUFF_TEMPLATES,
)
