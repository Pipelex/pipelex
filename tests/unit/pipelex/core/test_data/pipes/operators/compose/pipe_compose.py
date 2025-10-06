from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory

PIPE_COMPOSE = (
    "pipe_compose",
    """domain = "test_pipes"
description = "Domain with template processing pipe"

[pipe.process_template]
type = "PipeCompose"
description = "Process a Jinja2 template"
output = "Text"
jinja2 = "Hello {{ name }}!"
template_category = "markdown"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        description="Domain with template processing pipe",
        pipe={
            "process_template": PipeComposeBlueprint(
                type="PipeCompose",
                description="Process a Jinja2 template",
                output=NativeConceptCode.TEXT,
                jinja2="Hello {{ name }}!",
                template_category=Jinja2TemplateCategory.MARKDOWN,
            ),
        },
    ),
)

# Export all PipeCompose test cases
PIPE_COMPOSE_TEST_CASES = [
    PIPE_COMPOSE,
]
