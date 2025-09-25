from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint

SIMPLE_CONCEPTS = (
    "simple_concept",
    """domain = "simple_concept"
definition = "A simple concept"

[concept]
Concept1 = "A concept"
Concept2 = "A concept"
""",
    PipelexBundleBlueprint(
        domain="simple_concept",
        definition="A simple concept",
        concept={
            "Concept1": "A concept",
            "Concept2": "A concept",
        },
    ),
)

EMPTY_CONCEPTS = (
    "empty_concepts",
    """domain = "empty_concepts"
definition = "Domain with empty concept section"
""",
    PipelexBundleBlueprint(domain="empty_concepts", definition="Domain with empty concept section", concept={}),
)

# Export all simple concept test cases
SIMPLE_CONCEPT_TEST_CASES = [
    SIMPLE_CONCEPTS,
    EMPTY_CONCEPTS,
]
