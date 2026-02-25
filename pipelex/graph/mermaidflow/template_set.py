"""Mermaid template set definition.

This module defines the templates used for Mermaid HTML generation.
These templates are registered at boot time for sandbox-safe rendering.
"""

# Template set name
MERMAID_TEMPLATE_SET_NAME = "mermaid"

# Package path where templates are located
MERMAID_TEMPLATES_PACKAGE = "pipelex.graph.mermaidflow.templates"

# List of (filename, registry_key) tuples
MERMAID_TEMPLATES = [
    # Main templates
    ("mermaid_basic.html.jinja2", "mermaid/basic.html.jinja2"),
    ("mermaid_interactive.html.jinja2", "mermaid/interactive.html.jinja2"),
    # Basic partials
    ("_basic_head.html.jinja2", "mermaid/_basic_head.html.jinja2"),
    ("_basic_styles.css.jinja2", "mermaid/_basic_styles.css.jinja2"),
    ("_basic_body.html.jinja2", "mermaid/_basic_body.html.jinja2"),
    ("_basic_scripts.js.jinja2", "mermaid/_basic_scripts.js.jinja2"),
    # Interactive partials
    ("_interactive_head.html.jinja2", "mermaid/_interactive_head.html.jinja2"),
    ("_interactive_styles.css.jinja2", "mermaid/_interactive_styles.css.jinja2"),
    ("_interactive_body.html.jinja2", "mermaid/_interactive_body.html.jinja2"),
    ("_interactive_scripts.js.jinja2", "mermaid/_interactive_scripts.js.jinja2"),
]

# Tuple of (name, package, templates) for convenient single import
MERMAID_TEMPLATE_SET = (MERMAID_TEMPLATE_SET_NAME, MERMAID_TEMPLATES_PACKAGE, MERMAID_TEMPLATES)
