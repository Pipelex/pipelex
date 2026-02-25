"""ReactFlow template set definition.

This module defines the templates used for ReactFlow HTML generation.
These templates are registered at boot time for sandbox-safe rendering.
"""

# Template set name
REACTFLOW_TEMPLATE_SET_NAME = "reactflow"

# Package path where templates are located
REACTFLOW_TEMPLATES_PACKAGE = "pipelex.graph.reactflow.templates"

# List of (filename, registry_key) tuples
REACTFLOW_TEMPLATES = [
    ("reactflow.html.jinja2", "reactflow/main.html.jinja2"),
    ("_head.html.jinja2", "reactflow/_head.html.jinja2"),
    ("_styles.css.jinja2", "reactflow/_styles.css.jinja2"),
    ("_body.html.jinja2", "reactflow/_body.html.jinja2"),
    ("_scripts.js.jinja2", "reactflow/_scripts.js.jinja2"),
]

# Tuple of (name, package, templates) for convenient single import
REACTFLOW_TEMPLATE_SET = (REACTFLOW_TEMPLATE_SET_NAME, REACTFLOW_TEMPLATES_PACKAGE, REACTFLOW_TEMPLATES)
