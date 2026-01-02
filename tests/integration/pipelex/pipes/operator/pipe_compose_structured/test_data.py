"""Test data for PipeCompose structured content integration tests.

Contains construct blueprint dictionaries used across multiple test modules.
"""

from typing import Any, ClassVar


class ComposeStructuredTestData:
    """Test data for PipeCompose construct integration tests."""

    # Test case: all fixed values
    FIXED_ONLY_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "title": "Annual Report",
        "author": "John Doe",
        "score": 95.5,
    }

    # Test case: mix of fixed values and variable references
    MIXED_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "report_title": "Monthly Sales Report",
        "customer_name": {"from": "deal.customer_name"},
        "deal_value": {"from": "deal.amount"},
        "summary_text": {"template": "Deal worth $deal.amount with $deal.customer_name"},
    }

    # Test case: nested construct
    NESTED_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "name": {"from": "company_name"},
        "headquarters": {
            "street": {"from": "addr.street"},
            "city": {"from": "addr.city"},
            "country": "France",
        },
    }


class ContentConversionTestData:
    """Test data for content type conversion tests."""

    # Test case: TextContent to str field
    TEXT_TO_STR_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "title": {"from": "title_text"},
        "author": "Test Author",
    }

    # Test case: TextContent to TextContent field
    TEXT_TO_TEXT_CONTENT_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "title_content": {"from": "title_text"},
        "description": "A description",
    }

    # Test case: MarkdownText (TextContent subclass) to MarkdownText field
    MARKDOWN_TO_MARKDOWN_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "markdown_content": {"from": "markdown_input"},
        "summary": "Plain text summary",
    }

    # Test case: ListContent to list[TeamMember] field
    LIST_TO_LIST_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "team_name": "Engineering Team",
        "members": {"from": "team_members"},
    }

    # Test case: ListContent to ListContent field
    LIST_TO_LIST_CONTENT_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "team_name": "Engineering Team",
        "members_list": {"from": "team_members"},
    }


class ClassCompatibilityTestData:
    """Test data for class compatibility tests."""

    # Subclass to base class: RichTextContent -> TextContent field
    SUBCLASS_TO_BASE_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "content": {"from": "rich_text"},
        "note": "Testing subclass to base conversion",
    }

    # Class equivalence: list[Employee] items -> list[Person] field
    # (Employee and Person have same structure)
    EQUIVALENT_LIST_ITEMS_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "team_name": "Equivalent Team",
        "members": {"from": "employees"},
    }

    # Subclass list items: list[Manager] -> list[Person] field
    # (Manager is a subclass of Person)
    SUBCLASS_LIST_ITEMS_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "team_name": "Manager Team",
        "members": {"from": "managers"},
    }

    # Subclass list items in ListContent: ListContent[Manager] -> ListContent[Person]
    SUBCLASS_LIST_CONTENT_ITEMS_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "team_name": "ListContent Manager Team",
        "members": {"from": "managers_list"},
    }

    # Mixed subclass items: list[Product | DiscountedProduct] -> list[Product]
    MIXED_SUBCLASS_ITEMS_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "catalog_name": "Mixed Products Catalog",
        "products": {"from": "mixed_products"},
    }


class StructuredCompatibilityTestData:
    """Test data for direct StructuredContent class compatibility tests."""

    # Exact type match: Person -> PersonHolder.person field
    EXACT_TYPE_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "holder_name": "Exact Type Holder",
        "person": {"from": "input_person"},
    }

    # Class equivalence: Employee -> PersonHolder.person field
    # Employee and Person have the same fields (name, role)
    EQUIVALENT_CLASS_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "holder_name": "Equivalent Class Holder",
        "person": {"from": "input_employee"},
    }

    # Reverse equivalence: Person -> EmployeeHolder.employee field
    REVERSE_EQUIVALENT_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "holder_name": "Reverse Equivalent Holder",
        "employee": {"from": "input_person"},
    }

    # Subclass to base: Manager -> PersonHolder.person field
    SUBCLASS_TO_BASE_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "holder_name": "Subclass to Base Holder",
        "person": {"from": "input_manager"},
    }

    # Incompatible classes: Location -> PersonHolder.person field (should fail)
    INCOMPATIBLE_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "holder_name": "Incompatible Holder",
        "person": {"from": "input_location"},
    }
