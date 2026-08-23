from typing import Any, ClassVar

from pipelex.builder.concept.concept_spec import ConceptSpec, ConceptStructureSpec, ConceptStructureSpecFieldType
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint, ConceptStructureBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprintFieldType


class ConceptBlueprintTestCases:
    SIMPLE_CONCEPT = (
        "simple_concept",
        ConceptSpec(
            concept_code="ConceptCode",
            description="A simple test concept",
            refines=None,
            structure=None,
        ),
        ConceptBlueprint(
            description="A simple test concept",
            refines=None,
            structure=None,
        ),
    )

    CONCEPT_WITH_REFINES = (
        "concept_with_refines",
        ConceptSpec(
            concept_code="ConceptCode",
            description="An enhanced text concept",
            refines="Text",
            structure=None,
        ),
        ConceptBlueprint(
            description="An enhanced text concept",
            refines="Text",
            structure=None,
        ),
    )

    CONCEPT_WITH_TEXT_FIELD = (
        "concept_with_text_field",
        ConceptSpec(
            concept_code="ConceptCode",
            description="Entity with text field",
            structure={
                "name": ConceptStructureSpec(
                    the_field_name="name",
                    description="The name field",
                    type=ConceptStructureSpecFieldType.TEXT,
                    required=True,
                ),
            },
        ),
        ConceptBlueprint(
            description="Entity with text field",
            refines=None,
            structure={
                "name": ConceptStructureBlueprint(
                    description="The name field",
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
            concept_code="ConceptCode",
            description="Entity with integer field",
            structure={
                "age": ConceptStructureSpec(
                    the_field_name="age",
                    description="The age field",
                    type=ConceptStructureSpecFieldType.INTEGER,
                    required=False,
                    default_value=0,
                ),
            },
        ),
        ConceptBlueprint(
            description="Entity with integer field",
            refines=None,
            structure={
                "age": ConceptStructureBlueprint(
                    description="The age field",
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
            concept_code="ConceptCode",
            description="Entity with multiple fields",
            structure={
                "name": ConceptStructureSpec(
                    the_field_name="name",
                    description="Name",
                    type=ConceptStructureSpecFieldType.TEXT,
                    required=True,
                ),
                "age": ConceptStructureSpec(
                    the_field_name="age",
                    description="Age",
                    type=ConceptStructureSpecFieldType.INTEGER,
                    required=True,
                ),
                "active": ConceptStructureSpec(
                    the_field_name="active",
                    description="Active status",
                    type=ConceptStructureSpecFieldType.BOOLEAN,
                    required=False,
                    default_value=True,
                ),
            },
        ),
        ConceptBlueprint(
            description="Entity with multiple fields",
            refines=None,
            structure={
                "name": ConceptStructureBlueprint(
                    description="Name",
                    type=ConceptStructureBlueprintFieldType.TEXT,
                    required=True,
                    default_value=None,
                ),
                "age": ConceptStructureBlueprint(
                    description="Age",
                    type=ConceptStructureBlueprintFieldType.INTEGER,
                    required=True,
                ),
                "active": ConceptStructureBlueprint(
                    description="Active status",
                    type=ConceptStructureBlueprintFieldType.BOOLEAN,
                    required=False,
                    default_value=True,
                ),
            },
        ),
    )

    CONCEPT_WITH_CONCEPT_REF = (
        "concept_with_concept_ref",
        ConceptSpec(
            concept_code="Invoice",
            description="An invoice with a customer reference",
            structure={
                "invoice_number": ConceptStructureSpec(
                    the_field_name="invoice_number",
                    description="The invoice number",
                    type=ConceptStructureSpecFieldType.TEXT,
                    required=True,
                ),
                "customer": ConceptStructureSpec(
                    the_field_name="customer",
                    description="The customer for this invoice",
                    type=ConceptStructureSpecFieldType.CONCEPT,
                    concept_ref="myapp.Customer",
                    required=True,
                ),
            },
        ),
        ConceptBlueprint(
            description="An invoice with a customer reference",
            refines=None,
            structure={
                "invoice_number": ConceptStructureBlueprint(
                    description="The invoice number",
                    type=ConceptStructureBlueprintFieldType.TEXT,
                    required=True,
                    default_value=None,
                ),
                "customer": ConceptStructureBlueprint(
                    description="The customer for this invoice",
                    type=ConceptStructureBlueprintFieldType.CONCEPT,
                    concept_ref="myapp.Customer",
                    required=True,
                    default_value=None,
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
        CONCEPT_WITH_CONCEPT_REF,
    ]


class ConceptStructureSpecChoicesTestCases:
    """Test cases for choices field behavior in ConceptStructureSpec."""

    # choices without type -> defaults to text
    CHOICES_NO_TYPE = (
        "choices_no_type",
        {
            "the_field_name": "status",
            "description": "Order status",
            "choices": ["pending", "processing", "completed"],
            "required": True,
        },
        ConceptStructureSpecFieldType.TEXT,
        ["pending", "processing", "completed"],
    )

    # choices with explicit text type
    CHOICES_TEXT_TYPE = (
        "choices_text_type",
        {
            "the_field_name": "priority",
            "description": "Priority level",
            "type": "text",
            "choices": ["low", "medium", "high"],
        },
        ConceptStructureSpecFieldType.TEXT,
        ["low", "medium", "high"],
    )

    # choices with integer type
    CHOICES_INTEGER_TYPE = (
        "choices_integer_type",
        {
            "the_field_name": "rating",
            "description": "Star rating",
            "type": "integer",
            "choices": ["1", "2", "3", "4", "5"],
        },
        ConceptStructureSpecFieldType.INTEGER,
        ["1", "2", "3", "4", "5"],
    )

    # choices with number type
    CHOICES_NUMBER_TYPE = (
        "choices_number_type",
        {
            "the_field_name": "score",
            "description": "Score on a half-point scale",
            "type": "number",
            "choices": ["0", "0.5", "1", "1.5", "2"],
        },
        ConceptStructureSpecFieldType.NUMBER,
        ["0", "0.5", "1", "1.5", "2"],
    )

    VALID_CASES: ClassVar[list[tuple[str, dict[str, Any], ConceptStructureSpecFieldType, list[str]]]] = [
        CHOICES_NO_TYPE,
        CHOICES_TEXT_TYPE,
        CHOICES_INTEGER_TYPE,
        CHOICES_NUMBER_TYPE,
    ]

    # Incompatible types for choices
    CHOICES_BOOLEAN_TYPE = (
        "choices_boolean_type",
        {
            "the_field_name": "flag",
            "description": "A flag",
            "type": "boolean",
            "choices": ["true", "false"],
        },
    )

    CHOICES_DATE_TYPE = (
        "choices_date_type",
        {
            "the_field_name": "date_field",
            "description": "A date",
            "type": "date",
            "choices": ["2024-01-01", "2024-06-01"],
        },
    )

    CHOICES_CONCEPT_TYPE = (
        "choices_concept_type",
        {
            "the_field_name": "ref_field",
            "description": "A reference",
            "type": "concept",
            "concept_ref": "myapp.Customer",
            "choices": ["a", "b"],
        },
    )

    CHOICES_LIST_TYPE = (
        "choices_list_type",
        {
            "the_field_name": "list_field",
            "description": "A list",
            "type": "list",
            "item_type": "text",
            "choices": ["a", "b"],
        },
    )

    INCOMPATIBLE_CASES: ClassVar[list[tuple[str, dict[str, Any]]]] = [
        CHOICES_BOOLEAN_TYPE,
        CHOICES_DATE_TYPE,
        CHOICES_CONCEPT_TYPE,
        CHOICES_LIST_TYPE,
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

    # Test case: multi-segment domain path -> splits on last dot
    MULTI_SEGMENT_DOMAIN = (
        "multi_segment_domain",
        "legal.contracts.Invoice",
        "legal.contracts.Invoice",
    )

    # Test case: multi-segment domain with snake_case concept -> PascalCase
    MULTI_SEGMENT_DOMAIN_SNAKE = (
        "multi_segment_domain_snake",
        "legal.contracts.non_compete_clause",
        "legal.contracts.NonCompeteClause",
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
        MULTI_SEGMENT_DOMAIN,
        MULTI_SEGMENT_DOMAIN_SNAKE,
    ]
