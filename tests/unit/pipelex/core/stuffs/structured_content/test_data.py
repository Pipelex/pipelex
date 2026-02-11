from typing import Any, ClassVar

from pipelex.core.stuffs.structured_content import StructuredContent


class SampleStructuredContent(StructuredContent):
    """Test subclass for StructuredContent testing."""

    name: str
    value: int
    description: str | None = None


class AddressContent(StructuredContent):
    """Nested structured content for address."""

    street: str
    city: str


class PersonContent(StructuredContent):
    """Structured content with a nested StructuredContent field."""

    name: str
    age: int
    address: AddressContent


class CompanyContent(StructuredContent):
    """Structured content with a list of nested StructuredContent."""

    company_name: str
    employees: list[PersonContent]


class TestData:
    # Input content
    SAMPLE_NAME = "Test Item"
    SAMPLE_VALUE = 42
    SAMPLE_DESCRIPTION = "A test item description"

    # Expected outputs for smart_dump (minimal)
    EXPECTED_SMART_DUMP_MINIMAL: ClassVar[dict[str, Any]] = {"name": "Test Item", "value": 42, "description": None}

    # Expected outputs for smart_dump (with optional fields)
    EXPECTED_SMART_DUMP_FULL: ClassVar[dict[str, Any]] = {"name": "Test Item", "value": 42, "description": "A test item description"}

    # Expected outputs for render methods
    # convert_to_markdown produces headers for each key
    EXPECTED_RENDERED_MARKDOWN_MINIMAL = "# name: Test Item\n\n# value: 42\n\n# description: None"
    EXPECTED_RENDERED_MARKDOWN_FULL = "# name: Test Item\n\n# value: 42\n\n# description: A test item description"

    # Expected HTML outputs (table format, skips None values)
    EXPECTED_RENDERED_HTML_MINIMAL = "<table><tr><th>name</th><td>Test Item</td></tr><tr><th>value</th><td>42</td></tr></table>"
    EXPECTED_RENDERED_HTML_FULL = (
        "<table><tr><th>name</th><td>Test Item</td></tr><tr><th>value</th><td>42</td></tr>"
        "<tr><th>description</th><td>A test item description</td></tr></table>"
    )

    # Nested structured content test data
    NESTED_ADDRESS_STREET = "123 Main St"
    NESTED_ADDRESS_CITY = "Springfield"
    NESTED_PERSON_NAME = "John Doe"
    NESTED_PERSON_AGE = 30
    NESTED_COMPANY_NAME = "Acme Corp"

    # Expected HTML for AddressContent
    EXPECTED_ADDRESS_HTML = "<table><tr><th>street</th><td>123 Main St</td></tr><tr><th>city</th><td>Springfield</td></tr></table>"

    # Expected HTML for PersonContent (address field renders as nested table)
    EXPECTED_PERSON_HTML = (
        "<table><tr><th>name</th><td>John Doe</td></tr>"
        "<tr><th>age</th><td>30</td></tr>"
        "<tr><th>address</th><td><table><tr><th>street</th><td>123 Main St</td></tr>"
        "<tr><th>city</th><td>Springfield</td></tr></table></td></tr></table>"
    )

    # Expected HTML for CompanyContent with one employee
    EXPECTED_COMPANY_ONE_EMPLOYEE_HTML = (
        "<table><tr><th>company_name</th><td>Acme Corp</td></tr>"
        "<tr><th>employees</th><td><ul><li>"
        "<table><tr><th>name</th><td>John Doe</td></tr>"
        "<tr><th>age</th><td>30</td></tr>"
        "<tr><th>address</th><td><table><tr><th>street</th><td>123 Main St</td></tr>"
        "<tr><th>city</th><td>Springfield</td></tr></table></td></tr></table>"
        "</li></ul></td></tr></table>"
    )
