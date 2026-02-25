from typing import Any

import pytest

from pipelex.core.stuffs.text_content import TextContent
from tests.unit.pipelex.core.stuffs.text_content.test_data import TestData


class TestTextContentSmartDump:
    """Tests for TextContent.smart_dump() method."""

    def test_smart_dump_returns_dict(self):
        """Verify smart_dump always returns a dict, never a string."""
        content = TextContent(text=TestData.SAMPLE_TEXT)
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP
        assert isinstance(result, dict)

    def test_smart_dump_with_markdown_content(self):
        """Verify smart_dump correctly serializes markdown text."""
        content = TextContent(text=TestData.SAMPLE_TEXT_WITH_MARKDOWN)
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP_WITH_MARKDOWN
        assert isinstance(result, dict)

    @pytest.mark.parametrize(
        ("text_input", "expected_output"),
        [
            ("", {"text": ""}),
            ("   ", {"text": "   "}),
            ("line1\nline2", {"text": "line1\nline2"}),
            ("<html>test</html>", {"text": "<html>test</html>"}),
        ],
    )
    def test_smart_dump_various_inputs(self, text_input: str, expected_output: dict[str, Any]):
        """Verify smart_dump handles various text inputs correctly."""
        content = TextContent(text=text_input)
        result = content.smart_dump()
        assert result == expected_output
        assert isinstance(result, dict)
