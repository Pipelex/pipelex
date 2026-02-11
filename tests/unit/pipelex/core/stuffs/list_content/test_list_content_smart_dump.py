from __future__ import annotations

from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.text_content import TextContent
from tests.unit.pipelex.core.stuffs.list_content.test_data import TestData


class TestListContentSmartDump:
    """Tests for ListContent.smart_dump() method."""

    def test_smart_dump_returns_dict(self):
        """Verify smart_dump returns a dict with items list."""
        content: ListContent[TextContent] = ListContent(items=TestData.SAMPLE_TEXT_ITEMS)
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP
        assert isinstance(result, dict)

    def test_smart_dump_empty_list(self):
        """Verify smart_dump handles empty list correctly."""
        content: ListContent[TextContent] = ListContent(items=[])
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP_EMPTY
        assert isinstance(result, dict)

    def test_smart_dump_single_item(self):
        """Verify smart_dump handles single item list correctly."""
        content: ListContent[TextContent] = ListContent(items=[TextContent(text="Single")])
        result = content.smart_dump()
        assert result == {"items": [{"text": "Single"}]}
        assert isinstance(result, dict)
