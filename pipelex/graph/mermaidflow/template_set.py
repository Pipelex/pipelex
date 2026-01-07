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
    ("mermaid_pipelex.html.jinja2", "mermaid/pipelex.html.jinja2"),
    ("mermaid_interactive.html.jinja2", "mermaid/interactive.html.jinja2"),
]
