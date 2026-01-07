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
    ("mermaid_pipelex.html.jinja2", "mermaid/pipelex.html.jinja2"),
    ("mermaid_interactive.html.jinja2", "mermaid/interactive.html.jinja2"),
    # Pipelex partials
    ("_pipelex_head.html.jinja2", "mermaid/_pipelex_head.html.jinja2"),
    ("_pipelex_styles.css.jinja2", "mermaid/_pipelex_styles.css.jinja2"),
    ("_pipelex_body.html.jinja2", "mermaid/_pipelex_body.html.jinja2"),
    ("_pipelex_scripts.js.jinja2", "mermaid/_pipelex_scripts.js.jinja2"),
    # Interactive partials
    ("_interactive_head.html.jinja2", "mermaid/_interactive_head.html.jinja2"),
    ("_interactive_styles.css.jinja2", "mermaid/_interactive_styles.css.jinja2"),
    ("_interactive_body.html.jinja2", "mermaid/_interactive_body.html.jinja2"),
    ("_interactive_scripts.js.jinja2", "mermaid/_interactive_scripts.js.jinja2"),
]
