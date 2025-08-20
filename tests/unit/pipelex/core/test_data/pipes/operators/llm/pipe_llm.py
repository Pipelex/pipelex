"""PipeLLM test cases."""

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_operators.pipe_llm_factory import PipeLLMBlueprint

PIPE_LLM = (
    "pipe_llm",
    """domain = "test_pipes"
definition = "Domain with pipe definitions"

[pipe.generate_text]
type = "PipeLLM"
definition = "Generate text using LLM"
output = "Text"
prompt_template = "Generate a story about a programmer"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        definition="Domain with pipe definitions",
        pipe={
            "generate_text": PipeLLMBlueprint(
                type="PipeLLM",
                definition="Generate text using LLM",
                output="Text",
                prompt_template="Generate a story about a programmer",
            ),
        },
    ),
)

# Export all PipeLLM test cases
PIPE_LLM_TEST_CASES = [
    PIPE_LLM,
]
