"""Structured concept test cases."""

from pipelex.core.bundle.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concept.concept_blueprint import ConceptBlueprint, ConceptStructureBlueprint

CONCEPTS_WITH_STRUCTURES = (
    "concepts_with_structures",
    """domain = "structured_concepts"
definition = "Domain with structured concepts"

[concepts]
SimpleData = "Simple data concept"

[concepts.PersonInfo]
definition = "Information about a person"

[concepts.PersonInfo.structure]
name = "The name of the person"
age = { type = "number", definition = "The age of the person", required = true }
birthdate = { type = "date", definition = "The birthdate of the person", required = true }
""",
    PipelexBundleBlueprint(
        domain="structured_concepts",
        definition="Domain with structured concepts",
        concepts={
            "SimpleData": "Simple data concept",
            "PersonInfo": ConceptBlueprint(
                definition="Information about a person",
                structure={
                    "name": "The name of the person",
                    "age": ConceptStructureBlueprint(type="number", definition="The age of the person", required=True),
                    "birthdate": ConceptStructureBlueprint(type="date", definition="The birthdate of the person", required=True),
                },
            ),
        },
    ),
)

# Export all structured concept test cases
STRUCTURED_CONCEPT_TEST_CASES = [
    CONCEPTS_WITH_STRUCTURES,
]
