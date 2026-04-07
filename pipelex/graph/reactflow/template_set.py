"""ReactFlow Jinja2 template set registration."""

REACTFLOW_TEMPLATE_SET_NAME = "reactflow"

REACTFLOW_TEMPLATES_PACKAGE = "pipelex.graph.reactflow.templates"

REACTFLOW_TEMPLATES = [
    ("reactflow.html.jinja2", "reactflow/main.html.jinja2"),
]

REACTFLOW_TEMPLATE_SET = (REACTFLOW_TEMPLATE_SET_NAME, REACTFLOW_TEMPLATES_PACKAGE, REACTFLOW_TEMPLATES)
