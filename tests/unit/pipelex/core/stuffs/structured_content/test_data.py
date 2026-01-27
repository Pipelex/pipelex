from typing import Any, ClassVar

from pipelex.core.stuffs.structured_content import StructuredContent


class SampleStructuredContent(StructuredContent):
    """Test subclass for StructuredContent testing."""

    name: str
    value: int
    description: str | None = None


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

    # Expected HTML outputs (json2html format)
    EXPECTED_RENDERED_HTML_MINIMAL = (
        "<table ><tr><th>name</th><td>Test Item</td></tr><tr><th>value</th><td>42</td></tr><tr><th>description</th><td>None</td></tr></table>"
    )
    EXPECTED_RENDERED_HTML_FULL = (
        "<table ><tr><th>name</th><td>Test Item</td></tr><tr><th>value</th><td>42</td></tr>"
        "<tr><th>description</th><td>A test item description</td></tr></table>"
    )
