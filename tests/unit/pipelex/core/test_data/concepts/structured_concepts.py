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

CONCEPTS_WITH_NAMED_STRUCTURES = (
    "concepts_with_named_structures",
    """domain = "named_structures"
definition = "Domain with concepts using named structure references"

[concepts]
BasicInfo = "Basic information concept"

[concepts.ProductInfo]
definition = "Information about a product"
structure = "ProductData"

[concepts.OrderInfo]
definition = "Information about an order"
structure = "OrderData"
""",
    PipelexBundleBlueprint(
        domain="named_structures",
        definition="Domain with concepts using named structure references",
        concepts={
            "BasicInfo": "Basic information concept",
            "ProductInfo": ConceptBlueprint(
                definition="Information about a product",
                structure="ProductData",
            ),
            "OrderInfo": ConceptBlueprint(
                definition="Information about an order",
                structure="OrderData",
            ),
        },
    ),
)

# Export all structured concept test cases
STRUCTURED_CONCEPT_TEST_CASES = [
    CONCEPTS_WITH_STRUCTURES,
    CONCEPTS_WITH_NAMED_STRUCTURES,
]
