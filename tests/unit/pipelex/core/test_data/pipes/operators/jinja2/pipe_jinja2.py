from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_native import NativeConceptEnum
from pipelex.pipe_operators.jinja2.pipe_jinja2_blueprint import PipeJinja2Blueprint

PIPE_JINJA2 = (
    "pipe_jinja2",
    """domain = "test_pipes"
definition = "Domain with template processing pipe"

[pipe.process_template]
type = "PipeJinja2"
definition = "Process a Jinja2 template"
output = "Text"
jinja2 = "Hello {{ name }}!"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        definition="Domain with template processing pipe",
        pipe={
            "process_template": PipeJinja2Blueprint(
                type="PipeJinja2",
                definition="Process a Jinja2 template",
                output=NativeConceptEnum.TEXT,
                jinja2="Hello {{ name }}!",
            ),
        },
    ),
)

# Export all PipeJinja2 test cases
PIPE_JINJA2_TEST_CASES = [
    PIPE_JINJA2,
]
