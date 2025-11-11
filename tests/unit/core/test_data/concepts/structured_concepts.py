from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType

CONCEPTS_WITH_STRUCTURES = (
    "concepts_with_structures",
    """domain = "structured_concepts"
description = "Domain with structured concepts"

[concept]
SimpleData = "Simple data concept"

[concept.PersonInfo]
description = "Information about a person"

[concept.PersonInfo.structure]
name = "The name of the person"
age = { type = "number", description = "The age of the person", required = true }
birthdate = { type = "date", description = "The birthdate of the person", required = true }
""",
    PipelexBundleBlueprint(
        domain="structured_concepts",
        description="Domain with structured concepts",
        concept={
            "SimpleData": "Simple data concept",
            "PersonInfo": ConceptBlueprint(
                description="Information about a person",
                structure={
                    "name": "The name of the person",
                    "age": ConceptStructureBlueprint(
                        type=ConceptStructureBlueprintFieldType.NUMBER,
                        description="The age of the person",
                        required=True,
                    ),
                    "birthdate": ConceptStructureBlueprint(
                        type=ConceptStructureBlueprintFieldType.DATE,
                        description="The birthdate of the person",
                        required=True,
                    ),
                },
            ),
        },
    ),
)

CONCEPTS_WITH_NAMED_STRUCTURES = (
    "concepts_with_named_structures",
    """domain = "named_structures"
description = "Domain with concepts using named structure references"

[concept]
BasicInfo = "Basic information concept"

[concept.ProductInfo]
description = "Information about a product"
structure = "ProductData"

[concept.OrderInfo]
description = "Information about an order"
structure = "OrderData"
""",
    PipelexBundleBlueprint(
        domain="named_structures",
        description="Domain with concepts using named structure references",
        concept={
            "BasicInfo": "Basic information concept",
            "ProductInfo": ConceptBlueprint(
                description="Information about a product",
                structure="ProductData",
            ),
            "OrderInfo": ConceptBlueprint(
                description="Information about an order",
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
