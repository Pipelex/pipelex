"""
Test data for ConceptBlueprint conversion tests.
"""

from typing import ClassVar, List, Tuple

from pipelex.core.concepts.concept_blueprint import (
    ConceptBlueprint as ConceptBlueprintCore,
)
from pipelex.core.concepts.concept_blueprint import (
    ConceptStructureBlueprint as ConceptStructureBlueprintCore,
)
from pipelex.core.concepts.concept_blueprint import (
    ConceptStructureBlueprintFieldType as ConceptStructureBlueprintFieldTypeCore,
)
from pipelex.libraries.pipelines.builder.concept.concept import (
    ConceptBlueprint,
    ConceptStructureBlueprint,
    ConceptStructureBlueprintFieldType,
)


class ConceptBlueprintTestCases:
    """Test cases for ConceptBlueprint.to_core_blueprint conversion."""

    SIMPLE_CONCEPT = (
        "simple_concept",
        ConceptBlueprint(
            definition="A simple test concept",
            refines=None,
            structure=None,
        ),
        ConceptBlueprintCore(
            definition="A simple test concept",
            refines=None,
            structure=None,
        ),
    )

    CONCEPT_WITH_REFINES = (
        "concept_with_refines",
        ConceptBlueprint(
            definition="An enhanced text concept",
            refines="Text",
            structure=None,
        ),
        ConceptBlueprintCore(
            definition="An enhanced text concept",
            refines="Text",
            structure=None,
        ),
    )

    CONCEPT_WITH_TEXT_FIELD = (
        "concept_with_text_field",
        ConceptBlueprint(
            definition="Entity with text field",
            structure={
                "name": ConceptStructureBlueprint(
                    definition="The name field",
                    type=ConceptStructureBlueprintFieldType.TEXT,
                    required=True,
                ),
            },
        ),
        ConceptBlueprintCore(
            definition="Entity with text field",
            refines=None,
            structure={
                "name": ConceptStructureBlueprintCore(
                    definition="The name field",
                    type=ConceptStructureBlueprintFieldTypeCore.TEXT,
                    required=True,
                    default_value=None,
                ),
            },
        ),
    )

    CONCEPT_WITH_INTEGER_FIELD = (
        "concept_with_integer_field",
        ConceptBlueprint(
            definition="Entity with integer field",
            structure={
                "age": ConceptStructureBlueprint(
                    definition="The age field",
                    type=ConceptStructureBlueprintFieldType.INTEGER,
                    required=False,
                    default_value=0,
                ),
            },
        ),
        ConceptBlueprintCore(
            definition="Entity with integer field",
            refines=None,
            structure={
                "age": ConceptStructureBlueprintCore(
                    definition="The age field",
                    type=ConceptStructureBlueprintFieldTypeCore.INTEGER,
                    required=False,
                    default_value=0,
                ),
            },
        ),
    )

    CONCEPT_WITH_MULTIPLE_FIELDS = (
        "concept_with_multiple_fields",
        ConceptBlueprint(
            definition="Entity with multiple fields",
            structure={
                "name": ConceptStructureBlueprint(
                    definition="Name",
                    type=ConceptStructureBlueprintFieldType.TEXT,
                    required=True,
                ),
                "age": ConceptStructureBlueprint(
                    definition="Age",
                    type=ConceptStructureBlueprintFieldType.INTEGER,
                    required=True,
                    default_value=18,
                ),
                "active": ConceptStructureBlueprint(
                    definition="Active status",
                    type=ConceptStructureBlueprintFieldType.BOOLEAN,
                    required=False,
                    default_value=True,
                ),
            },
        ),
        ConceptBlueprintCore(
            definition="Entity with multiple fields",
            refines=None,
            structure={
                "name": ConceptStructureBlueprintCore(
                    definition="Name",
                    type=ConceptStructureBlueprintFieldTypeCore.TEXT,
                    required=True,
                    default_value=None,
                ),
                "age": ConceptStructureBlueprintCore(
                    definition="Age",
                    type=ConceptStructureBlueprintFieldTypeCore.INTEGER,
                    required=True,
                    default_value=18,
                ),
                "active": ConceptStructureBlueprintCore(
                    definition="Active status",
                    type=ConceptStructureBlueprintFieldTypeCore.BOOLEAN,
                    required=False,
                    default_value=True,
                ),
            },
        ),
    )

    # Collect all test cases
    TEST_CASES: ClassVar[List[Tuple[str, ConceptBlueprint, ConceptBlueprintCore]]] = [
        SIMPLE_CONCEPT,
        CONCEPT_WITH_REFINES,
        CONCEPT_WITH_TEXT_FIELD,
        CONCEPT_WITH_INTEGER_FIELD,
        CONCEPT_WITH_MULTIPLE_FIELDS,
    ]
