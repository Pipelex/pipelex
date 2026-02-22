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
""",
    PipelexBundleBlueprint(
        domain="system_prompt_test",
        description="A domain with system prompts",
        system_prompt="You are an expert assistant",
    ),
)

HIERARCHICAL_DOMAIN = (
    "hierarchical_domain",
    """domain = "legal.contracts"
description = "A hierarchical domain for legal contracts"
""",
    PipelexBundleBlueprint(
        domain="legal.contracts",
        description="A hierarchical domain for legal contracts",
    ),
)

DEEP_HIERARCHICAL_DOMAIN = (
    "deep_hierarchical_domain",
    """domain = "legal.contracts.shareholder"
description = "A deeply nested hierarchical domain"
""",
    PipelexBundleBlueprint(
        domain="legal.contracts.shareholder",
        description="A deeply nested hierarchical domain",
    ),
)

# Export all domain test cases
DOMAIN_TEST_CASES = [
    SIMPLE_DOMAIN,
    DOMAIN_WITH_SYSTEM_PROMPTS,
    HIERARCHICAL_DOMAIN,
    DEEP_HIERARCHICAL_DOMAIN,
]
