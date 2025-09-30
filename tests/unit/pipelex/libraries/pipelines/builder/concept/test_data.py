from typing import ClassVar

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint, ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.libraries.pipelines.builder.concept.concept_spec import ConceptSpec, ConceptStructureSpec, ConceptStructureSpecFieldType


class ConceptBlueprintTestCases:
    SIMPLE_CONCEPT = (
        "simple_concept",
        ConceptSpec(
            the_concept_code="ConceptCode",
            definition="A simple test concept",
            refines=None,
            structure=None,
        ),
        ConceptBlueprint(
            definition="A simple test concept",
            refines=None,
            structure=None,
        ),
    )

    CONCEPT_WITH_REFINES = (
        "concept_with_refines",
        ConceptSpec(
            the_concept_code="ConceptCode",
            definition="An enhanced text concept",
            refines="Text",
            structure=None,
        ),
        ConceptBlueprint(
            definition="An enhanced text concept",
            refines="Text",
            structure=None,
        ),
    )

    CONCEPT_WITH_TEXT_FIELD = (
        "concept_with_text_field",
        ConceptSpec(
            the_concept_code="ConceptCode",
            definition="Entity with text field",
            structure={
                "name": ConceptStructureSpec(
                    the_field_name="name",
                    definition="The name field",
                    type=ConceptStructureSpecFieldType.TEXT,
                    required=True,
                ),
            },
        ),
        ConceptBlueprint(
            definition="Entity with text field",
            refines=None,
            structure={
                "name": ConceptStructureBlueprint(
                    definition="The name field",
                    type=ConceptStructureBlueprintFieldType.TEXT,
                    required=True,
                    default_value=None,
                ),
            },
        ),
    )

    CONCEPT_WITH_INTEGER_FIELD = (
        "concept_with_integer_field",
        ConceptSpec(
            the_concept_code="ConceptCode",
            definition="Entity with integer field",
            structure={
                "age": ConceptStructureSpec(
                    the_field_name="age",
                    definition="The age field",
                    type=ConceptStructureSpecFieldType.INTEGER,
                    required=False,
                    default_value=0,
                ),
            },
        ),
        ConceptBlueprint(
            definition="Entity with integer field",
            refines=None,
            structure={
                "age": ConceptStructureBlueprint(
                    definition="The age field",
                    type=ConceptStructureBlueprintFieldType.INTEGER,
                    required=False,
                    default_value=0,
                ),
            },
        ),
    )

    CONCEPT_WITH_MULTIPLE_FIELDS = (
        "concept_with_multiple_fields",
        ConceptSpec(
            the_concept_code="ConceptCode",
            definition="Entity with multiple fields",
            structure={
                "name": ConceptStructureSpec(
                    the_field_name="name",
                    definition="Name",
                    type=ConceptStructureSpecFieldType.TEXT,
                    required=True,
                ),
                "age": ConceptStructureSpec(
                    the_field_name="age",
                    definition="Age",
                    type=ConceptStructureSpecFieldType.INTEGER,
                    required=True,
                    default_value=18,
                ),
                "active": ConceptStructureSpec(
                    the_field_name="active",
                    definition="Active status",
                    type=ConceptStructureSpecFieldType.BOOLEAN,
                    required=False,
                    default_value=True,
                ),
            },
        ),
        ConceptBlueprint(
            definition="Entity with multiple fields",
            refines=None,
            structure={
                "name": ConceptStructureBlueprint(
                    definition="Name",
                    type=ConceptStructureBlueprintFieldType.TEXT,
                    required=True,
                    default_value=None,
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
    )

    TEST_CASES: ClassVar[list[tuple[str, ConceptSpec, ConceptBlueprint]]] = [
        SIMPLE_CONCEPT,
        CONCEPT_WITH_REFINES,
        CONCEPT_WITH_TEXT_FIELD,
        CONCEPT_WITH_INTEGER_FIELD,
        CONCEPT_WITH_MULTIPLE_FIELDS,
    ]


class ConceptCodeValidationTestCases:
    """Test cases for concept code validation and snake_case to PascalCase conversion."""

    # Test case: snake_case without domain -> PascalCase
    SNAKE_CASE_NO_DOMAIN = (
        "snake_case_no_domain",
        "concept_name",
        "ConceptName",
    )

    # Test case: PascalCase without domain -> unchanged
    PASCAL_CASE_NO_DOMAIN = (
        "pascal_case_no_domain",
        "ConceptName",
        "ConceptName",
    )

    # Test case: snake_case with domain -> domain.PascalCase
    SNAKE_CASE_WITH_DOMAIN = (
        "snake_case_with_domain",
        "my_domain.concept_name",
        "my_domain.ConceptName",
    )

    # Test case: PascalCase with domain -> unchanged
    PASCAL_CASE_WITH_DOMAIN = (
        "pascal_case_with_domain",
        "my_domain.ConceptName",
        "my_domain.ConceptName",
    )

    # Test case: mixed case with domain -> domain.PascalCase
    MIXED_CASE_WITH_DOMAIN = (
        "mixed_case_with_domain",
        "my_domain.some_complex_concept_name",
        "my_domain.SomeComplexConceptName",
    )

    # Test case: single word snake_case -> PascalCase
    SINGLE_WORD_SNAKE = (
        "single_word_snake",
        "concept",
        "Concept",
    )

    # Test case: multiple underscores -> PascalCase
    MULTIPLE_UNDERSCORES = (
        "multiple_underscores",
        "my_super_long_concept_name",
        "MySuperLongConceptName",
    )

    # Test case: with numbers in snake_case
    WITH_NUMBERS_SNAKE = (
        "with_numbers_snake",
        "concept_v2_name",
        "ConceptV2Name",
    )

    # Test case: with numbers in domain.snake_case
    WITH_NUMBERS_DOMAIN_SNAKE = (
        "with_numbers_domain_snake",
        "domain_v1.concept_name_v2",
        "domain_v1.ConceptNameV2",
    )

    TEST_CASES: ClassVar[list[tuple[str, str, str]]] = [
        SNAKE_CASE_NO_DOMAIN,
        PASCAL_CASE_NO_DOMAIN,
        SNAKE_CASE_WITH_DOMAIN,
        PASCAL_CASE_WITH_DOMAIN,
        MIXED_CASE_WITH_DOMAIN,
        SINGLE_WORD_SNAKE,
        MULTIPLE_UNDERSCORES,
        WITH_NUMBERS_SNAKE,
        WITH_NUMBERS_DOMAIN_SNAKE,
    ]
