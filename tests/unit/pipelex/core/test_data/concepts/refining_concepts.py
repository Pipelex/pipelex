from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint

CONCEPTS_WITH_REFINES = (
    "concepts_with_refines",
    """domain = "refining_concepts"
description = "Domain with concepts that refine others"

[concept]
Concept1 = "A concept1"
Concept2 = "A concept2"

[concept.Concept3]
description = "A concept3"
refines = "Image"
""",
    PipelexBundleBlueprint(
        domain="refining_concepts",
        description="Domain with concepts that refine others",
        concept={
            "Concept1": "A concept1",
            "Concept2": "A concept2",
            "Concept3": ConceptBlueprint(description="A concept3", refines="Image"),
        },
    ),
)

# Export all refining concept test cases
REFINING_CONCEPT_TEST_CASES = [
    CONCEPTS_WITH_REFINES,
]
