from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint

PIPE_COMPOSE_WITHOUT_CATEGORY = (
    "pipe_compose_without_category",
    """domain = "test_pipes"
description = "Domain with template processing pipe"

[pipe.process_template]
type = "PipeCompose"
description = "Process a Jinja2 template"
output = "Text"
template = "Hello {{ name }}!"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        description="Domain with template processing pipe",
        pipe={
            "process_template": PipeComposeBlueprint(
                type="PipeCompose",
                description="Process a Jinja2 template",
                output=NativeConceptCode.TEXT,
                template="Hello {{ name }}!",
            ),
        },
    ),
)

PIPE_COMPOSE_WITH_CATEGORY = (
    "pipe_compose",
    """domain = "test_pipes"
description = "Domain with template processing pipe"

[pipe.compose_output]
type = "PipeCompose"
description = "Process a Jinja2 template"
output = "Text"

[pipe.compose_output.template]
template = "Hello {{ name }}!"
category = "markdown"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        description="Domain with template processing pipe",
        pipe={
            "compose_output": PipeComposeBlueprint(
                type="PipeCompose",
                description="Process a Jinja2 template",
                output=NativeConceptCode.TEXT,
                template=TemplateBlueprint(
                    template="Hello {{ name }}!",
                    category=TemplateCategory.MARKDOWN,
                ),
            ),
        },
    ),
)

# Export all PipeCompose test cases
PIPE_COMPOSE_TEST_CASES = [
    PIPE_COMPOSE_WITHOUT_CATEGORY,
    PIPE_COMPOSE_WITH_CATEGORY,
]
