"""PipeTemplate test cases."""

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_operators.pipe_template_factory import PipeTemplateBlueprint

PIPE_TEMPLATE = (
    "pipe_template",
    """domain = "test_pipes"
definition = "Domain with template processing pipe"

[pipe.process_template]
type = "PipeJinja2"
definition = "Process a Jinja2 template"
output = "Text"
template = "Hello {{ name }}!"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        definition="Domain with template processing pipe",
        pipe={
            "process_template": PipeTemplateBlueprint(
                type="PipeTemplate",
                definition="Process a Jinja2 template",
                output="Text",
                template="Hello {{ name }}!",
            ),
        },
    ),
)

# Export all PipeTemplate test cases
PIPE_TEMPLATE_TEST_CASES = [
    PIPE_TEMPLATE,
]
