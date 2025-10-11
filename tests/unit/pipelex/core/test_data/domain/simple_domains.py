from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint

SIMPLE_DOMAIN = (
    "simple_domain",
    """domain = "simple_test"
description = "A simple test domain"
""",
    PipelexBundleBlueprint(
        domain="simple_test",
        description="A simple test domain",
    ),
)

DOMAIN_WITH_SYSTEM_PROMPTS = (
    "domain_with_system_prompts",
    """domain = "system_prompt_test"
description = "A domain with system prompts"
system_prompt = "You are an expert assistant"
system_prompt_to_structure = "Generate structured output"
prompt_template_to_structure = "Structure the following data: ..."
""",
    PipelexBundleBlueprint(
        domain="system_prompt_test",
        description="A domain with system prompts",
        system_prompt="You are an expert assistant",
        system_prompt_to_structure="Generate structured output",
        prompt_template_to_structure="Structure the following data: ...",
    ),
)

# Export all domain test cases
DOMAIN_TEST_CASES = [
    SIMPLE_DOMAIN,
    DOMAIN_WITH_SYSTEM_PROMPTS,
]
