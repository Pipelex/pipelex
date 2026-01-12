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


class StuffContentSubclassTestData:
    """Test data for StuffContent subclass composition tests (ImageContent, DocumentContent, etc.)."""

    # ImageContent composition
    IMAGE_GALLERY_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "gallery_name": "Nature Gallery",
        "cover_image": {"from": "cover"},
        "featured_image": {"from": "featured"},
    }

    IMAGE_GALLERY_SINGLE_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "gallery_name": "Simple Gallery",
        "cover_image": {"from": "cover"},
    }

    # DocumentContent composition
    DOCUMENT_ARCHIVE_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "archive_name": "Legal Documents Archive",
        "main_document": {"from": "main_pdf"},
        "supplementary_doc": {"from": "supplement_pdf"},
    }

    DOCUMENT_ARCHIVE_SINGLE_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "archive_name": "Contract Archive",
        "main_document": {"from": "main_pdf"},
    }

    # NumberContent composition
    METRICS_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "metric_name": "Performance Metrics",
        "primary_value": {"from": "primary_metric"},
        "secondary_value": {"from": "secondary_metric"},
    }

    METRICS_SINGLE_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "metric_name": "Simple Metric",
        "primary_value": {"from": "primary_metric"},
    }

    # MermaidContent composition
    CODE_SNIPPET_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "snippet_name": "Architecture Diagram",
        "diagram": {"from": "mermaid_diagram"},
    }

    # HtmlContent composition
    WEB_CONTENT_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "content_title": "Homepage Section",
        "html_block": {"from": "html_content"},
    }

    # JSONContent composition
    DATA_PAYLOAD_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "payload_name": "API Response",
        "data": {"from": "json_data"},
    }

    # Mixed media composition (multiple StuffContent types)
    MIXED_MEDIA_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "report_title": "Annual Report",
        "cover_image": {"from": "cover"},
        "document": {"from": "main_pdf"},
        "view_count": {"from": "primary_metric"},
    }

    # List of ImageContent
    IMAGE_LIST_GALLERY_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "gallery_name": "Photo Collection",
        "images": {"from": "image_list"},
    }

    # List of DocumentContent
    DOCUMENT_BUNDLE_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "bundle_name": "Contract Bundle",
        "documents": {"from": "pdf_list"},
    }
